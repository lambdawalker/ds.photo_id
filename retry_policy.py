"""Bounded retry delays; persisted deadlines use wall-clock time across restarts."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RetryPolicy:
    enabled: bool = True
    max_retries: int = 3
    initial_delay_seconds: float = 10
    max_delay_seconds: float = 120

    @classmethod
    def from_config(cls, values):
        policy = cls(**values)
        if not isinstance(policy.enabled, bool):
            raise ValueError('retries.enabled must be true or false')
        if isinstance(policy.max_retries, bool) or not isinstance(policy.max_retries, int) or policy.max_retries < 0:
            raise ValueError('retries.max_retries must be a nonnegative integer')
        for value in (policy.initial_delay_seconds, policy.max_delay_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Retry delays must be positive finite numbers')
        if policy.max_delay_seconds < policy.initial_delay_seconds:
            raise ValueError('Maximum retry delay must be at least the initial delay')
        return policy

    def delay(self, failure_count):
        if not self.enabled or failure_count > self.max_retries:
            return None
        return min(self.max_delay_seconds, self.initial_delay_seconds * 2 ** min(failure_count - 1, 30))
