"""knndm.py docstring: 'CAST draws n labels without replacement from rep(1:k, ceiling(n/k)) ... for n <= (k - 1)^2, a
fold can be empty'. A fold can be empty iff all ceiling(n/k) copies of its label can be among the k*ceiling(n/k) - n
labels left undrawn, i.e. iff ceiling(n/k) <= k*ceiling(n/k) - n. Enumerated for k = 5 and 10 (n >= k + 2)."""
import math
for k in (5, 10):
    can = [n for n in range(k + 2, (k - 1) ** 2 + 1) if math.ceil(n / k) <= k * math.ceil(n / k) - n]
    cannot = [n for n in range(k + 2, (k - 1) ** 2 + 1) if n not in can]
    above = [n for n in range((k - 1) ** 2 + 1, k * k + 1) if math.ceil(n / k) <= k * math.ceil(n / k) - n]
    print(f"k={k}: n <= (k-1)^2={(k-1)**2} where a fold CAN be empty: {can}; where it CANNOT: {cannot}; above (k-1)^2: {above}")
