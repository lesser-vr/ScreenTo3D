"""Owned public still, repeatedly repainted to exercise real WGC RGB reuse."""
def source_main(connection, source, interval_ms=16):
    from PySide6.QtGui import QPainter
    from benchmark_live_modes import ClockOracle
    from live_benchmark_source import source_main as run
    advance=ClockOracle.advance

    def still_advance(self):
        if self.video_frame is None:
            advance(self)
        else:
            self.update()

    def still_paint(self,event):
        self.paint_count+=1
        painter=QPainter(self)
        if self.video_frame is not None:
            painter.drawImage(self.rect(),self.video_frame)
        painter.end()

    ClockOracle.advance=still_advance
    ClockOracle.paintEvent=still_paint
    run(connection,source,interval_ms)
