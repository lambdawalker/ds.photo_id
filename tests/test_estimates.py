import unittest
from processing_estimates import duration, estimate


class EstimateTests(unittest.TestCase):
    def test_image_bottleneck_is_not_sum_of_concurrent_workers(self):
        prompt, total = estimate(100, 100, 100, 64,
                                 {'llm': 2, 'original': 50, 'background': 10}, has_ready=True)
        self.assertEqual(total, 6000)
        self.assertGreater(prompt, 200)  # producer waits for queue space

    def test_slow_llm_includes_last_image_tail(self):
        _, total = estimate(10, 10, 10, 64, {'llm': 100, 'original': 5, 'background': 1})
        self.assertEqual(total, 1006)

    def test_existing_originals_only_need_background_time(self):
        prompt, total = estimate(0, 3, 0, 64, {'background': 10})
        self.assertEqual((prompt, total), (0, 30))

    def test_waits_for_measurements_and_deducts_active_time(self):
        self.assertIsNone(estimate(1, 1, 1, 64, {})[1])
        self.assertEqual(estimate(0, 2, 2, 64, {'original': 20, 'background': 5}, {'original': 8})[1], 42)
        self.assertEqual(estimate(0, 0, 0, 64, {}), (0, 0))

    def test_duration_does_not_wrap_at_one_day(self):
        self.assertEqual(duration(90000), '1d 01h 00m')
        self.assertEqual(duration(.1), '1s')


class PersistentTimingsTests(unittest.TestCase):
    def test_recent_timings_survive_restart(self):
        import copy
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from generation_session import Session
        from test_generation import CONFIG
        with TemporaryDirectory() as root:
            session = Session(copy.deepcopy(CONFIG), Path(root))
            for value in range(40):
                session.record_time('original', value + 1)
            session.close()
            session = Session(copy.deepcopy(CONFIG), Path(root))
            try:
                self.assertEqual(session.db.execute('SELECT COUNT(*) FROM timings').fetchone()[0], 30)
                self.assertEqual(session.averages()['original'], 25.5)
            finally:
                session.close()
