"""
Easing functions for smooth animations.

These functions take a progress value t in [0, 1] and return
an eased value, creating natural-feeling motion.
"""
import math
from typing import Tuple


def lerp(a: float, b: float, t: float) -> float:
    """
    Linear interpolation between a and b.

    Args:
        a: Start value
        b: End value
        t: Progress (0-1)

    Returns:
        Interpolated value
    """
    return a + (b - a) * t


def ease_in_quad(t: float) -> float:
    """Quadratic ease-in: accelerating from zero."""
    return t * t


def ease_out_quad(t: float) -> float:
    """Quadratic ease-out: decelerating to zero."""
    return 1 - (1 - t) * (1 - t)


def ease_in_out_quad(t: float) -> float:
    """Quadratic ease-in-out: acceleration until halfway, then deceleration."""
    if t < 0.5:
        return 2 * t * t
    else:
        return 1 - math.pow(-2 * t + 2, 2) / 2


def ease_in_cubic(t: float) -> float:
    """Cubic ease-in: accelerating from zero."""
    return t * t * t


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out: decelerating to zero."""
    return 1 - math.pow(1 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out: acceleration until halfway, then deceleration."""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - math.pow(-2 * t + 2, 3) / 2


def ease_in_sine(t: float) -> float:
    """Sine ease-in: smooth start."""
    return 1 - math.cos((t * math.pi) / 2)


def ease_out_sine(t: float) -> float:
    """Sine ease-out: smooth end."""
    return math.sin((t * math.pi) / 2)


def ease_in_out_sine(t: float) -> float:
    """Sine ease-in-out: smooth start and end."""
    return -(math.cos(math.pi * t) - 1) / 2


def ease_out_elastic(t: float) -> float:
    """Elastic ease-out: overshoots and bounces back."""
    if t == 0 or t == 1:
        return t

    c4 = (2 * math.pi) / 3
    return math.pow(2, -10 * t) * math.sin((t * 10 - 0.75) * c4) + 1


def ease_out_bounce(t: float) -> float:
    """Bounce ease-out: bouncing effect at the end."""
    n1 = 7.5625
    d1 = 2.75

    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1
        return n1 * t * t + 0.984375


def smooth_damp(
    current: float,
    target: float,
    current_velocity: float,
    smooth_time: float,
    delta_time: float,
    max_speed: float = float('inf')
) -> Tuple[float, float]:
    """
    Smoothly interpolate towards a target value.
    Similar to Unity's SmoothDamp function.

    Args:
        current: Current value
        target: Target value
        current_velocity: Current velocity (modified by this function)
        smooth_time: Approximate time to reach target
        delta_time: Time since last call
        max_speed: Maximum speed

    Returns:
        Tuple of (new_value, new_velocity)
    """
    # Avoid divide by zero
    smooth_time = max(0.0001, smooth_time)
    omega = 2.0 / smooth_time

    x = omega * delta_time
    exp = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)

    change = current - target
    original_to = target

    # Clamp maximum speed
    max_change = max_speed * smooth_time
    change = max(-max_change, min(max_change, change))
    target = current - change

    temp = (current_velocity + omega * change) * delta_time
    new_velocity = (current_velocity - omega * temp) * exp
    output = target + (change + temp) * exp

    # Prevent overshooting
    if (original_to - current > 0.0) == (output > original_to):
        output = original_to
        new_velocity = (output - original_to) / delta_time

    return output, new_velocity


def spring_interpolate(
    current: float,
    target: float,
    velocity: float,
    stiffness: float = 50.0,
    damping: float = 10.0,
    delta_time: float = 1/60
) -> Tuple[float, float]:
    """
    Spring-based interpolation for bouncy movement.

    Args:
        current: Current value
        target: Target value
        velocity: Current velocity
        stiffness: Spring stiffness (higher = faster)
        damping: Damping factor (higher = less bouncy)
        delta_time: Time step

    Returns:
        Tuple of (new_value, new_velocity)
    """
    # Spring force
    force = -stiffness * (current - target)
    # Damping force
    force -= damping * velocity

    # Update velocity and position
    new_velocity = velocity + force * delta_time
    new_value = current + new_velocity * delta_time

    return new_value, new_velocity
