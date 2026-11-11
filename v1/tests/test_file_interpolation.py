import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
import numpy as np
from depthsbs_app.file_interpolation import DoubleRate
from depthsbs_app import pipeline


class FileInterpolationTests(unittest.TestCase):
    def frame(self,value):return np.full((16,32,3),value,np.uint8)

    def test_original_timestamps_and_duration_with_cut_repetition_and_tail(self):
        generate=Mock(side_effect=lambda a,b:((a.astype(np.uint16)+b)//2).astype(np.uint8))
        cadence=DoubleRate(generate)
        values=[]
        for color,cut in ((0,False),(200,True),(210,False)):
            values.extend(int(frame[0,0,0]) for frame in cadence.submit(self.frame(color),cut_before=cut))
        values.extend(int(frame[0,0,0]) for frame in cadence.finish())
        self.assertEqual(values,[0,0,200,205,210,210])
        self.assertEqual(len(values),2*cadence.originals);generate.assert_called_once()
        self.assertEqual(cadence.telemetry()['cut_repeats'],1)
        self.assertEqual(cadence.telemetry()['tail_repeats'],1)
        self.assertEqual(cadence.finish(),())

    def test_single_frame_gets_a_tail_and_empty_input_emits_nothing(self):
        cadence=DoubleRate(Mock())
        self.assertEqual(len(cadence.submit(self.frame(7)))+len(cadence.finish()),2)
        self.assertEqual(DoubleRate(Mock()).finish(),())

    def test_previous_frame_owns_its_pixels(self):
        original=self.frame(8);generate=Mock(side_effect=lambda a,b:a)
        cadence=DoubleRate(generate);cadence.submit(original);original.fill(100)
        result=cadence.submit(self.frame(9))
        self.assertTrue(np.all(result[0]==8))

    def test_bad_shapes_or_results_fail(self):
        cadence=DoubleRate(lambda a,b:np.zeros((1,1),np.uint8));cadence.submit(self.frame(0))
        with self.assertRaises(ValueError):cadence.submit(self.frame(1))
        with self.assertRaises(ValueError):cadence.submit(np.zeros((17,32,3),np.uint8))
        with self.assertRaises(ValueError):DoubleRate(Mock()).submit(np.zeros((16,32,3),np.float32))

    def run_pipeline(self,folder,*,vfg=False,strength=1.,fail=False,layout='full-sbs'):
        metadata=dict(width=160,height=90,fps=30000/1001,total_frames=2)
        texture=np.broadcast_to(np.arange(160,dtype=np.uint8)[None,:,None],(90,160,3)).copy()
        frames=np.stack([texture,texture+4])
        decoder=Mock(stdout=io.BytesIO(frames.tobytes()),stderr=io.BytesIO())
        class Writer(io.BytesIO):
            def close(inner):
                if not inner.closed:inner.result=inner.getvalue()
                super().close()
        writer=Writer();encoder=Mock(stdin=writer,stderr=io.BytesIO())
        for process in (decoder,encoder):process.wait.return_value=0;process.poll.return_value=0
        engine=Mock();engine.infer.return_value=np.linspace(0,1,518*518,dtype=np.float32).reshape(1,518,518)
        engine.telemetry.return_value={}
        context=Mock(__enter__=Mock(return_value=engine),__exit__=Mock(return_value=False))
        interpolator=Mock();interpolator.generate.side_effect=RuntimeError('test VFG failure') if fail else lambda a,b:((a.astype(np.uint16)+b)//2).astype(np.uint8)
        interpolator.telemetry.return_value={}
        interpolation_context=Mock(__enter__=Mock(return_value=interpolator),__exit__=Mock(return_value=False))
        def mux(arguments):
            Path(arguments[-1]).write_bytes(b'new media')
            return subprocess.CompletedProcess(arguments,0,'','')
        output=Path(folder)/'output.mp4'
        with patch.object(pipeline,'probe_video',return_value=metadata),patch.object(pipeline,'DepthEngine',return_value=context), \
                patch.object(pipeline.subprocess,'Popen',side_effect=[decoder,encoder]) as spawn,patch.object(pipeline,'_run',side_effect=mux):
            result=pipeline.convert_video(Path(folder)/'source.mp4',output,'performance',lambda e:None,
                vfg=vfg,depth_strength=strength,stereo_layout=layout,interpolation_factory=lambda w,h:interpolation_context)
        return result,spawn.call_args_list[1].args[0],writer,interpolator,interpolation_context

    def test_pipeline_vfg_doubles_cfr_and_frame_count_with_no_duration_change(self):
        with tempfile.TemporaryDirectory() as folder:
            result,args,writer,interpolator,context=self.run_pipeline(folder,vfg=True)
        self.assertEqual(result['frames'],4)
        self.assertAlmostEqual(result['output_fps'],60000/1001)
        self.assertEqual(args[args.index('-r')+1],f'{60000/1001:.8f}')
        self.assertEqual(len(writer.result),4*160*2*90*3)
        self.assertEqual(result['vfg']['generated_frames'],1)
        context.__exit__.assert_called_once()

    def test_strength_scales_disparity_and_off_keeps_original_frame_cadence(self):
        with tempfile.TemporaryDirectory() as folder:
            result,_,_,interpolator,_=self.run_pipeline(folder,strength=.5)
        self.assertEqual(result['frames'],2);self.assertFalse(result['vfg']['enabled'])
        self.assertEqual(result['policy']['divergence'],pipeline.MODES['performance'].divergence*.5)
        interpolator.generate.assert_not_called()

    def test_strength_changes_actual_stereo_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            _,_,half,_,_=self.run_pipeline(folder,strength=.5)
            _,_,full,_,_=self.run_pipeline(folder,strength=2.)
        self.assertTrue(half.result!=full.result,'Stereo pixels must change across the supported strength range')

    def test_vfg_packs_all_four_output_formats_after_interpolation(self):
        for layout,(width,height) in {'full-sbs':(320,90),'half-sbs':(160,90),'full-tb':(160,180),'half-tb':(160,90)}.items():
            with self.subTest(layout=layout),tempfile.TemporaryDirectory() as folder:
                result,_,writer,_,_=self.run_pipeline(folder,vfg=True,layout=layout)
            self.assertEqual((result['output_width'],result['output_height']),(width,height))
            self.assertEqual(len(writer.result),width*height*3*4)

    def test_interpolation_failure_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'output.mp4';output.write_bytes(b'previous output')
            with self.assertRaisesRegex(RuntimeError,'test VFG failure'):self.run_pipeline(folder,vfg=True,fail=True)
            self.assertEqual(output.read_bytes(),b'previous output')

    def test_invalid_strength_or_vfg_fails_before_probe(self):
        for value in (float('nan'),float('inf'),True,0,2.1):
            with patch.object(pipeline,'probe_video') as probe,self.assertRaises(ValueError):
                pipeline.convert_video(Path('a'),Path('b'),'balanced',lambda e:None,depth_strength=value)
            probe.assert_not_called()
