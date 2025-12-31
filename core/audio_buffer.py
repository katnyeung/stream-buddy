"""
Audio buffer for WebM streaming with header extraction.
Handles chunked audio data from MediaRecorder.
"""
import tempfile
import os


def find_cluster_offset(data: bytes) -> int:
    """Find the offset of the first Cluster element in WebM data."""
    cluster_id = b'\x1f\x43\xb6\x75'
    pos = data.find(cluster_id)
    return pos if pos != -1 else len(data)


class AudioBuffer:
    def __init__(self):
        self.chunks: list[bytes] = []
        self.stored_header: bytes | None = None
        self.accumulated_chunks: list[bytes] = []
        self.total_bytes = 0

    def append(self, chunk: bytes) -> None:
        """Append audio chunk to buffer."""
        self.chunks.append(chunk)
        self.accumulated_chunks.append(chunk)
        self.total_bytes += len(chunk)

        # Extract header from first chunk if not stored
        if self.stored_header is None and len(self.chunks) == 1:
            offset = find_cluster_offset(chunk)
            if offset > 0:
                self.stored_header = chunk[:offset]

    def get_accumulated_with_header(self) -> bytes:
        """Get all accumulated audio data with WebM header prepended."""
        if not self.accumulated_chunks:
            return b''

        data = b''.join(self.accumulated_chunks)

        # If we have a stored header and the data doesn't start with EBML
        if self.stored_header and not data.startswith(b'\x1a\x45\xdf\xa3'):
            return self.stored_header + data

        return data

    def clear_accumulator(self) -> None:
        """Clear accumulated chunks but keep the header."""
        self.accumulated_chunks = []

    def clear_all(self) -> None:
        """Clear all buffers."""
        self.chunks = []
        self.accumulated_chunks = []
        self.total_bytes = 0
        # Keep the header for reuse

    async def save_to_temp_file(self) -> str | None:
        """Save accumulated audio to a temporary file. Returns filepath or None."""
        data = self.get_accumulated_with_header()

        if len(data) < 1024:  # Skip if less than 1KB
            return None

        fd, filepath = tempfile.mkstemp(suffix='.webm')
        try:
            os.write(fd, data)
        finally:
            os.close(fd)

        return filepath
