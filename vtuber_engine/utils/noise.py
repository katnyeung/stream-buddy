"""
Noise generators for organic movement.

Perlin noise provides smooth, natural-looking random movement that
avoids sudden jumps - perfect for idle animations.
"""
import math
import random
from typing import List


class PerlinNoise:
    """
    1D Perlin noise generator for smooth random values.
    Used for organic idle movement (head sway, breathing variations).
    """

    def __init__(self, seed: int = None):
        """
        Initialize the noise generator.

        Args:
            seed: Random seed for reproducible noise
        """
        if seed is not None:
            random.seed(seed)

        # Generate permutation table
        self.perm = list(range(256))
        random.shuffle(self.perm)
        self.perm = self.perm + self.perm  # Double it to avoid overflow

    def _fade(self, t: float) -> float:
        """Smooth interpolation curve (6t^5 - 15t^4 + 10t^3)."""
        return t * t * t * (t * (t * 6 - 15) + 10)

    def _lerp(self, a: float, b: float, t: float) -> float:
        """Linear interpolation."""
        return a + t * (b - a)

    def _grad(self, hash_val: int, x: float) -> float:
        """Calculate gradient."""
        h = hash_val & 15
        grad = 1.0 + (h & 7)  # Gradient value 1-8
        if h & 8:
            grad = -grad
        return grad * x

    def noise(self, x: float) -> float:
        """
        Get 1D Perlin noise value at position x.

        Args:
            x: Position to sample noise

        Returns:
            Noise value in range [-1, 1]
        """
        # Find unit interval containing x
        xi = int(math.floor(x)) & 255
        xf = x - math.floor(x)

        # Compute fade curve
        u = self._fade(xf)

        # Hash coordinates
        a = self.perm[xi]
        b = self.perm[xi + 1]

        # Gradient values
        g1 = self._grad(a, xf)
        g2 = self._grad(b, xf - 1)

        # Interpolate
        return self._lerp(g1, g2, u)

    def octave_noise(self, x: float, octaves: int = 4, persistence: float = 0.5) -> float:
        """
        Multi-octave noise for more interesting patterns.

        Args:
            x: Position to sample
            octaves: Number of octaves to sum
            persistence: Amplitude decay per octave

        Returns:
            Noise value, approximately in [-1, 1]
        """
        total = 0.0
        frequency = 1.0
        amplitude = 1.0
        max_value = 0.0

        for _ in range(octaves):
            total += self.noise(x * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2.0

        return total / max_value


class SimplexNoise:
    """
    2D Simplex noise for smooth random values.
    Slightly faster than Perlin and produces better results in higher dimensions.
    """

    # Skewing factors for 2D
    F2 = 0.5 * (math.sqrt(3.0) - 1.0)
    G2 = (3.0 - math.sqrt(3.0)) / 6.0

    # Gradient vectors
    GRAD2 = [
        (1, 1), (-1, 1), (1, -1), (-1, -1),
        (1, 0), (-1, 0), (0, 1), (0, -1)
    ]

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)

        self.perm = list(range(256))
        random.shuffle(self.perm)
        self.perm = self.perm + self.perm

    def _dot2(self, g, x: float, y: float) -> float:
        return g[0] * x + g[1] * y

    def noise2d(self, x: float, y: float) -> float:
        """
        Get 2D simplex noise value.

        Args:
            x, y: Position to sample

        Returns:
            Noise value in range [-1, 1]
        """
        # Skew input space
        s = (x + y) * self.F2
        i = int(math.floor(x + s))
        j = int(math.floor(y + s))

        # Unskew back
        t = (i + j) * self.G2
        X0 = i - t
        Y0 = j - t
        x0 = x - X0
        y0 = y - Y0

        # Determine simplex
        if x0 > y0:
            i1, j1 = 1, 0
        else:
            i1, j1 = 0, 1

        x1 = x0 - i1 + self.G2
        y1 = y0 - j1 + self.G2
        x2 = x0 - 1.0 + 2.0 * self.G2
        y2 = y0 - 1.0 + 2.0 * self.G2

        # Hash indices
        ii = i & 255
        jj = j & 255
        gi0 = self.perm[ii + self.perm[jj]] % 8
        gi1 = self.perm[ii + i1 + self.perm[jj + j1]] % 8
        gi2 = self.perm[ii + 1 + self.perm[jj + 1]] % 8

        # Calculate contributions
        n0 = n1 = n2 = 0.0

        t0 = 0.5 - x0 * x0 - y0 * y0
        if t0 >= 0:
            t0 *= t0
            n0 = t0 * t0 * self._dot2(self.GRAD2[gi0], x0, y0)

        t1 = 0.5 - x1 * x1 - y1 * y1
        if t1 >= 0:
            t1 *= t1
            n1 = t1 * t1 * self._dot2(self.GRAD2[gi1], x1, y1)

        t2 = 0.5 - x2 * x2 - y2 * y2
        if t2 >= 0:
            t2 *= t2
            n2 = t2 * t2 * self._dot2(self.GRAD2[gi2], x2, y2)

        # Scale to [-1, 1]
        return 70.0 * (n0 + n1 + n2)


class MultiNoiseGenerator:
    """
    Generates multiple noise channels for different body parts.
    Each channel has independent noise for natural, uncorrelated movement.
    """

    def __init__(self, num_channels: int = 8, seed: int = None):
        """
        Initialize multi-channel noise generator.

        Args:
            num_channels: Number of independent noise channels
            seed: Base seed (each channel gets seed + channel_id)
        """
        base_seed = seed if seed is not None else random.randint(0, 10000)
        self.generators = [
            PerlinNoise(seed=base_seed + i)
            for i in range(num_channels)
        ]
        self.time_offsets = [
            random.uniform(0, 1000) for _ in range(num_channels)
        ]

    def get_noise(self, channel: int, time: float, speed: float = 1.0) -> float:
        """
        Get noise value for a specific channel.

        Args:
            channel: Channel index
            time: Time value
            speed: Speed multiplier

        Returns:
            Noise value in [-1, 1]
        """
        if channel >= len(self.generators):
            channel = channel % len(self.generators)

        t = (time + self.time_offsets[channel]) * speed
        return self.generators[channel].octave_noise(t, octaves=3, persistence=0.5)
