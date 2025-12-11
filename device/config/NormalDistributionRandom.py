import numpy as np

# 尝试导入 scipy，如果不存在则使用纯 numpy 实现
try:
    from scipy.stats import truncnorm
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


class NormalDistributionRandom:
    def __init__(self, min_value: float, max_value: float, median: float, std: float = None):
        """
        初始化正态分布随机数生成器
        
        Args:
            min_value: 最小值
            max_value: 最大值
            median: 中位数（期望值）
            std: 标准差，如果为None，则自动计算为范围的1/6（使得99.7%的值在范围内）
        """
        if min_value >= max_value:
            raise ValueError("最小值必须小于最大值")
        if not (min_value <= median <= max_value):
            raise ValueError("中位数必须在最小值和最大值之间")
        
        self.min_value = min_value
        self.max_value = max_value
        self.median = median
        
        # 如果没有指定标准差，则根据范围自动计算
        # 使用3倍标准差规则，使得99.7%的值在范围内
        if std is None:
            # 计算到两端的距离，取较小值作为3倍标准差
            distance_to_min = median - min_value
            distance_to_max = max_value - median
            # 使用较小的距离来确保分布不会超出范围
            self.std = min(distance_to_min, distance_to_max) / 3.0
        else:
            self.std = std
        
        # 计算截断正态分布的参数
        # truncnorm 使用标准化的边界 (a, b)，其中 a = (min - mean) / std, b = (max - mean) / std
        self.a = (min_value - median) / self.std
        self.b = (max_value - median) / self.std
        
        # 创建截断正态分布对象（如果 scipy 可用）
        if HAS_SCIPY:
            self.dist = truncnorm(self.a, self.b, loc=median, scale=self.std)
        else:
            self.dist = None  # 将使用纯 numpy 实现
    
    def random(self) -> float:
        """
        生成一个符合正态分布的随机数
        
        Returns:
            在 [min_value, max_value] 范围内的随机数，概率分布符合正态分布
        """
        if HAS_SCIPY and self.dist is not None:
            return float(self.dist.rvs())
        else:
            # 使用纯 numpy 实现：生成正态分布随机数，然后截断到范围内
            # 使用拒绝采样方法，直到生成的值在范围内
            max_attempts = 1000
            for _ in range(max_attempts):
                value = np.random.normal(self.median, self.std)
                if self.min_value <= value <= self.max_value:
                    return float(value)
            # 如果多次尝试都失败，返回边界值（这种情况很少见）
            return float(np.clip(np.random.normal(self.median, self.std), self.min_value, self.max_value))
    
    def random_int(self) -> int:
        """
        生成一个符合正态分布的随机整数
        
        Returns:
            在 [min_value, max_value] 范围内的随机整数
        """
        return int(round(self.random()))
    
    def sample(self, size: int) -> np.ndarray:
        """
        生成多个符合正态分布的随机数
        
        Args:
            size: 要生成的随机数数量
            
        Returns:
            随机数数组
        """
        if HAS_SCIPY and self.dist is not None:
            return self.dist.rvs(size=size)
        else:
            # 使用纯 numpy 实现
            samples = []
            for _ in range(size):
                samples.append(self.random())
            return np.array(samples)


def normal_random(min_value: float, max_value: float, median: float, std: float = None) -> float:
    generator = NormalDistributionRandom(min_value, max_value, median, std)
    return generator.random()


def normal_random_int(min_value: int, max_value: int, median: float, std: float = None) -> int:
    generator = NormalDistributionRandom(min_value, max_value, median, std)
    return generator.random_int()
