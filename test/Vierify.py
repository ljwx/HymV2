import ast

from utils.json_cache import JsonCacheUtils

pos_str = "(1,2)"
print(tuple(ast.literal_eval(pos_str)))