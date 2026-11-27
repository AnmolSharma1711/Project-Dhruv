"""Pure conversion helpers (no ROS imports) so they can be unit-tested on a laptop."""
import math


def sanitize(v) -> float:
    """NaN / inf / None -> 0.0"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def to_power(v: float, per_unit: float, min_pwm: int, max_pwm: int, sign: int = 1) -> int:
    """
    Convert one velocity (m/s or rad/s) to a motor power integer.
    - |v| tiny            -> 0 (stop)
    - otherwise           -> at least min_pwm (below it the wheels only hum), at most max_pwm
    """
    v = sanitize(v) * (1 if sign >= 0 else -1)
    if abs(v) < 1e-3:
        return 0
    mag = max(min_pwm, min(max_pwm, abs(v) * per_unit))
    return int(round(math.copysign(mag, v)))


def twist_to_mix(vx, wz, pwm_per_mps, pwm_per_radps, min_pwm, max_pwm,
                 drive_sign=1, turn_sign=1):
    """
    Returns (Vx, Vy, W) for the Arduino <MIX,Vx,Vy,W> command.
    Vy (sideways) is ALWAYS 0: this robot only drives forward/backward and pivots.
    """
    a = to_power(vx, pwm_per_mps, min_pwm, max_pwm, drive_sign)
    c = to_power(wz, pwm_per_radps, min_pwm, max_pwm, turn_sign)
    return a, 0, c


def format_mix(vx_pwm: int, vy_pwm: int, w_pwm: int) -> str:
    return f'<MIX,{vx_pwm},{vy_pwm},{w_pwm}>'
