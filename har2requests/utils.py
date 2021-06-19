from typing import Optional


def dict_intersection(a: dict, b: dict):
    """Elements that are the same in a and b"""
    return {k: v for k, v in a.items() if k in b and b[k] == v}


def dict_change(a: dict, b: dict):
    """Elements of b that are not the same in a"""
    return {
        **{k: v for k, v in b.items() if k not in a or a[k] != v},
        **{k: None for k in a if a[k] is not None and k not in b},
    }


def dict_delete(a: dict, b: dict):
    """Elements that are in a but not in b"""
    return [k for k in a if k not in b]


def json_dfs(d: Optional[dict]):
    if d is None:
        return
    for k, v in d.items():
        if isinstance(v, dict):
            for kk, vv in json_dfs(v):
                yield (k,) + kk, vv
        else:
            yield (k,), v
