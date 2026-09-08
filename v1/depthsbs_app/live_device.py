"""Borrowed same-stream device output; not a transferable raw pointer API."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceDepth:
    owner: object
    generation: int
    pointer: int
    stream: int
    shape: tuple = (1, 518, 518)

    def validate(self):
        self.owner._device_check()
        if self.shape != (1, 518, 518):
            raise ValueError("Invalid device depth dimensions")
        if self.owner.device_generation != self.generation:
            raise RuntimeError("Device depth expired after another inference")
        if self.pointer != int(self.owner.device_output) or self.stream != int(
            self.owner.stream
        ):
            raise RuntimeError("Invalid borrowed depth binding")
