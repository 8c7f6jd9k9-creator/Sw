"""Ed25519 (RFC 8032, раздел 5.1) на чистом Python для подписи и проверки лицензий.

Встроенный runtime не содержит криптографических библиотек, поэтому используется
эталонный алгоритм RFC 8032 в расширенных координатах. Проверка подписи занимает
миллисекунды. Совместимость проверена тестовыми векторами RFC 8032 и сверкой
с независимой реализацией (tests/test_license.py).
"""
import hashlib

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _hash_mod_l(data):
    return int.from_bytes(hashlib.sha512(data).digest(), 'little') % _L


def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _multiply(scalar, point):
    result = (0, 1, 1, 0)
    while scalar > 0:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _equal(p, q):
    return (p[0] * q[2] - q[0] * p[2]) % _P == 0 and (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(point):
    inverse = pow(point[2], _P - 2, _P)
    x, y = point[0] * inverse % _P, point[1] * inverse % _P
    return (y | ((x & 1) << 255)).to_bytes(32, 'little')


def _decompress(data):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _expand(seed):
    if len(seed) != 32:
        raise ValueError('Закрытый ключ Ed25519 должен содержать 32 байта.')
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], 'little')
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def public_key(seed):
    scalar, _ = _expand(bytes(seed))
    return _compress(_multiply(scalar, _G))


def sign(seed, message):
    scalar, prefix = _expand(bytes(seed))
    public = _compress(_multiply(scalar, _G))
    r = _hash_mod_l(prefix + message)
    encoded_r = _compress(_multiply(r, _G))
    s = (r + _hash_mod_l(encoded_r + public + message) * scalar) % _L
    return encoded_r + s.to_bytes(32, 'little')


def verify(public, message, signature):
    """True только для подписи, созданной закрытым ключом, соответствующим public."""
    try:
        public, signature = bytes(public), bytes(signature)
    except (TypeError, ValueError):
        return False
    if len(public) != 32 or len(signature) != 64:
        return False
    point_a = _decompress(public)
    point_r = _decompress(signature[:32])
    if point_a is None or point_r is None:
        return False
    s = int.from_bytes(signature[32:], 'little')
    if s >= _L:
        return False
    h = _hash_mod_l(signature[:32] + public + message)
    return _equal(_multiply(s, _G), _add(point_r, _multiply(h, point_a)))
