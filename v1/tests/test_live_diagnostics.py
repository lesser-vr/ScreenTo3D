import json,multiprocessing as mp,unittest
from screento3d_app.live_diagnostics import FlightRecorder,WorkerDiagnostics

def record_in_child(shared):
 shared.observe(640,360,1,100,120,0)
 try:raise RuntimeError('HRESULT 0x887A0005')
 except RuntimeError as error:shared.failure(error)

class FlightRecorderTests(unittest.TestCase):
 def test_window_and_capacity_and_snapshot_are_bounded(self):
  recorder=FlightRecorder(clock=lambda:70_000_000_000)
  for i in range(71):recorder.sample({'frame':i},now=i*1_000_000_000)
  for i in range(200):recorder.event('resize',{'i':i},now=70_000_000_000)
  snapshot=recorder.snapshot(now=70_000_000_000)
  self.assertEqual(len(snapshot['samples']),61);self.assertEqual(snapshot['samples'][0]['state']['frame'],10)
  self.assertLessEqual(len(snapshot['events']),64)
  recorder.sample({'frame':999},now=71_000_000_000)
  self.assertEqual(snapshot['samples'][-1]['state']['frame'],70)
 def test_long_gap_discards_old_samples_and_events(self):
  r=FlightRecorder();r.sample({'frame':1},now=0);r.event('start',now=0)
  s=r.snapshot(now=61_000_000_000);self.assertEqual(s['samples'],[]);self.assertEqual(s['events'],[])
 def test_oversize_context_keeps_latest_and_reports_omission(self):
  r=FlightRecorder()
  for i in range(61):r.sample({'frame':i,'values':list(range(500))},now=i*1_000_000_000)
  s=r.snapshot(now=60_000_000_000,max_bytes=8192)
  self.assertLessEqual(len(json.dumps(s,ensure_ascii=False).encode()),8192)
  self.assertEqual(s['samples'][-1]['state']['frame'],60);self.assertGreater(s['omitted_samples'],0)
 def test_samples_are_copied_and_nonfinite_is_json_safe(self):
  r=FlightRecorder();state={'values':[1,float('nan')]};r.sample(state,now=0);state['values'][0]=99
  s=r.snapshot(now=0);self.assertEqual(s['samples'][0]['state']['values'][0],1)
  json.dumps(s,allow_nan=False)

class WorkerDiagnosticsTests(unittest.TestCase):
 def test_capture_intervals_resizes_and_clock_regression(self):
  d=WorkerDiagnostics.create(mp.get_context('spawn'))
  d.observe(640,360,1,10,100,0);d.observe(1280,720,3,50,200,1);d.observe(1280,720,4,20,210,1)
  s=d.snapshot();self.assertEqual(s['accepted_frames'],3);self.assertEqual(s['max_source_gap_ns'],40)
  self.assertEqual(s['max_callback_gap_ns'],100);self.assertEqual(s['source_clock_regressions'],1)
  self.assertEqual(s['resizes'],1);self.assertEqual((s['width'],s['height']),(1280,720))
 def test_error_stack_survives_without_changing_exception(self):
  d=WorkerDiagnostics.create(mp.get_context('spawn'))
  try:raise RuntimeError('HRESULT 0x887A0005 · 한글')
  except RuntimeError as e:d.failure(e)
  s=d.snapshot();self.assertEqual(s['failure']['type'],'RuntimeError');self.assertIn('0x887A0005',s['failure']['traceback'])
  self.assertIn('한글',s['failure']['message'])
 def test_torn_snapshot_never_waits_for_dead_writer(self):
  d=WorkerDiagnostics.create(mp.get_context('spawn'));d.state[0]=1
  self.assertIsNone(d.snapshot())
 def test_spawned_worker_preserves_metadata_and_traceback_after_exit(self):
  context=mp.get_context('spawn');shared=WorkerDiagnostics.create(context)
  child=context.Process(target=record_in_child,args=(shared,));child.start();child.join(10)
  try:
   self.assertFalse(child.is_alive());self.assertEqual(child.exitcode,0)
   snapshot=shared.snapshot();self.assertEqual(snapshot['sequence'],1)
   self.assertIn('record_in_child',snapshot['failure']['traceback'])
  finally:
   if child.is_alive():child.terminate();child.join(5)
   child.close()
 def test_failure_payload_stays_bounded(self):
  d=WorkerDiagnostics.create(mp.get_context('spawn'));d.failure(ValueError('한글'*40000))
  self.assertLess(len(d.error.value),16*1024);self.assertEqual(d.snapshot()['failure']['type'],'ValueError')

if __name__=='__main__':unittest.main()
