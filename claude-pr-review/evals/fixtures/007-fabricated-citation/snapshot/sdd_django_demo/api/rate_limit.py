DEFAULT_WINDOW_SECONDS = 60


def is_rate_limited(attempts, window=DEFAULT_WINDOW_SECONDS):
    return len(attempts) > 5
