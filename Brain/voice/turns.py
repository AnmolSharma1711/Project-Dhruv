"""Segment 16 kHz mono PCM into turns. All durations refer to 20 ms frames."""

from collections import deque


class Segmenter:
    def __init__(self, onset=6, silence=30, max_frames=6000):
        if not 1 <= onset <= 15 or not 1 <= silence < max_frames or max_frames <= 15:
            raise ValueError("Invalid speech timing")
        self.onset = onset
        self.silence = silence
        self.max_frames = max_frames
        self.pre = deque(maxlen=15)
        self.frames = []
        self.voiced = self.quiet = 0
        self.discard = False

    def feed(self, frame, speech):
        """Return (event, pcm); oversized utterances are discarded until silence."""
        self.quiet = 0 if speech else self.quiet + 1
        if self.discard:
            if self.quiet >= self.silence:
                self.discard = False
            return None, None
        if not self.frames:
            self.pre.append(frame)
            self.voiced = self.voiced + 1 if speech else 0
            if self.voiced < self.onset:
                return None, None
            self.frames = list(self.pre)
            self.pre.clear()
            self.voiced = 0
            return "onset", None
        self.frames.append(frame)
        if self.quiet >= self.silence:
            pcm = b"".join(self.frames)
            self.frames.clear()
            return "turn", pcm
        if len(self.frames) >= self.max_frames:
            self.frames.clear()
            self.discard = True
            return "too_long", None
        return None, None
