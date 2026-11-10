import unittest
from processing_estimates import duration, estimate, active_work


class EstimateTests(unittest.TestCase):
    def test_image_bottleneck_is_not_sum_of_concurrent_workers(self):
        prompt, total = estimate(100, 100, 100, 64,
                                 {'llm': 2, 'original': 50, 'background': 10}, has_ready=True)
        self.assertEqual(total, 6000)
        self.assertGreater(prompt, 200)  # producer waits for queue space

    def test_fast_llm_has_less_active_work_but_waits_for_full_queue(self):
        # Matches the screenshot's 131 prepared, 66 images, and a full queue.
        averages = {'llm': 3, 'original': 14, 'background': 1}
        pending, remaining = 10000 - 131, 10000 - 66
        llm_work, image_work = active_work(pending, remaining, remaining, averages)
        llm_finish, batch_finish = estimate(pending, remaining, remaining, 64, averages, has_ready=True)
        self.assertEqual(llm_work, pending * 3)
        self.assertEqual(image_work, remaining * 15)
        self.assertLess(llm_work, image_work / 4)
        self.assertLess(abs(batch_finish - llm_finish), batch_finish * .01)

    def test_unlimited_disk_queue_does_not_tie_llm_finish_to_images(self):
        averages = {'llm': 3, 'original': 14, 'background': 1}
        prompt_finish, image_finish = estimate(9869, 9934, 9934, None, averages, has_ready=True)
        self.assertEqual(prompt_finish, 9869 * 3)
        self.assertEqual(image_finish, 9934 * 15)

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
