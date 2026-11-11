import asyncio
import copy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from generation_session import Session, Pipeline
from photo_id_generator import ComfyGenerationError, compose_prompt
from test_generation import CONFIG, PNG, until


def config(max_retries=3):
    result=copy.deepcopy(CONFIG)
    result['generation']['samples']=1
    result['generation']['retries']={'enabled':True,'max_retries':max_retries,
                                     'initial_delay_seconds':.01,'max_delay_seconds':.04}
    return result


class AutoRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_polls_same_remote_job_and_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));events=[]
            pipeline=Pipeline(session,lambda stage,message:events.append(message))
            calls=[]
            def wait(remote,*args):
                calls.append(remote)
                if calls==['original']:raise TimeoutError('still working')
                return PNG
            with patch('generation_session.submit_image',return_value='original') as submit,patch('generation_session.submit_background',return_value='background'),patch('generation_session.wait_image',side_effect=wait):
                pipeline.start()
                await until(lambda:session.counts().get('done')==1)
                await pipeline.stop()
                self.assertEqual(submit.call_count,1)
            self.assertEqual(calls,['original','original','background'])
            self.assertFalse(pipeline.paused)
            self.assertTrue(any('Automatic retry 1/3' in message for message in events))
            self.assertEqual(session.next('done')['retry_count'],0)
            session.close()

    async def test_background_retry_reuses_saved_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));pipeline=Pipeline(session)
            def wait(remote,*args):
                if remote=='failed-background':raise ComfyGenerationError('GPU error')
                return PNG
            with patch('generation_session.submit_image',return_value='original') as submit,patch('generation_session.submit_background',side_effect=['failed-background','good-background']) as background,patch('generation_session.wait_image',side_effect=wait):
                pipeline.start();await until(lambda:session.counts().get('done')==1);await pipeline.stop()
                self.assertEqual(submit.call_count,1)
                self.assertEqual(background.call_count,2)
            self.assertEqual(session.paths(session.next('done'))[0].read_bytes(),PNG)
            session.close()

    async def test_retry_limit_is_bounded_and_manual_retry_resets_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(2),Path(tmp));pipeline=Pipeline(session)
            with patch('generation_session.submit_image',side_effect=TimeoutError('offline')) as submit:
                pipeline.start()
                await until(lambda:session.retry_snapshot()['exhausted']==1)
                await asyncio.sleep(.05)
                self.assertEqual(submit.call_count,3)
                self.assertFalse(pipeline.paused)
                await pipeline.stop()
            self.assertEqual(session.next('failed')['retry_count'],3)
            pipeline.retry()
            self.assertEqual(session.next('ready')['retry_count'],0)
            session.close()

    async def test_retry_deadline_and_count_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=config();session=Session(settings,Path(tmp));deadline=time.time()+30
            session.update(1,prompt='Saved prompt',state='failed',error='timeout',retry_count=2,
                           retry_at=deadline,failure_stage='image',remote_id='saved-job',remote_url='http://old')
            session.close();session=Session(settings,Path(tmp));pipeline=Pipeline(session)
            self.assertEqual(session.next('failed')['retry_at'],deadline)
            with patch('generation_session.time.time',return_value=deadline+.1),patch('generation_session.submit_image') as submit,patch('generation_session.submit_background',return_value='background'),patch('generation_session.wait_image',return_value=PNG):
                pipeline.start();await until(lambda:session.counts().get('done')==1);await pipeline.stop()
                submit.assert_not_called()
            session.close()

    async def test_pause_and_exit_do_not_dispatch_scheduled_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp));pipeline=Pipeline(session)
            with patch('generation_session.submit_image',side_effect=TimeoutError('offline')) as submit:
                pipeline.start();await until(lambda:session.retry_snapshot()['scheduled']==1)
                pipeline.pause();await asyncio.sleep(.06)
                self.assertEqual(submit.call_count,1)
                await asyncio.wait_for(pipeline.stop(),timeout=.5)
                self.assertEqual(submit.call_count,1)
            self.assertEqual(session.counts()['failed'],1)
            session.close()

    async def test_exhausted_job_does_not_stop_other_portraits(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=config(0);settings['generation']['samples']=2
            session=Session(settings,Path(tmp));pipeline=Pipeline(session)
            def submit(workflow,prompt,seed,stem,*args,**kwargs):
                if stem=='photoId_00001':raise TimeoutError('failed sample')
                return 'original'
            with patch('generation_session.submit_image',side_effect=submit),patch('generation_session.submit_background',return_value='background'),patch('generation_session.wait_image',return_value=PNG):
                pipeline.start();await until(lambda:session.counts().get('done')==1);await pipeline.stop()
            self.assertEqual(session.counts(),{'done':1,'failed':1})
            self.assertFalse(pipeline.paused)
            session.close()

    async def test_existing_failed_records_are_scheduled_on_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Session(config(),Path(tmp))
            saved_prompt=compose_prompt('Saved prompt')
            session.update(1,prompt=saved_prompt,state='failed',error='old failure')
            seed=session.next('failed')['image_seed'];session.close()
            session=Session(config(),Path(tmp))
            job=session.next('failed')
            self.assertEqual(job['retry_count'],1)
            self.assertEqual(job['failure_stage'],'image')
            self.assertIsNotNone(job['retry_at'])
            self.assertEqual(job['image_seed'],seed)
            self.assertEqual(job['prompt'],saved_prompt)
            session.close()


class RetryPolicyTests(unittest.TestCase):
    def test_default_backoff_and_limit(self):
        from retry_policy import RetryPolicy
        policy=RetryPolicy()
        self.assertEqual([policy.delay(i) for i in (1,2,3,4)],[10,20,40,None])
        self.assertEqual(RetryPolicy(max_delay_seconds=30).delay(3),30)
        self.assertIsNone(RetryPolicy(enabled=False).delay(1))

    def test_rejects_invalid_configuration(self):
        from retry_policy import RetryPolicy
        for values in ({'max_retries':-1},{'max_retries':True},{'initial_delay_seconds':0},
                       {'max_delay_seconds':float('inf')},{'initial_delay_seconds':20,'max_delay_seconds':10}):
            with self.assertRaises(ValueError):RetryPolicy.from_config(values)
