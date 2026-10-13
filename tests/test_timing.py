"""The latency pill must count Aito calls made from worker threads.

A `ThreadPoolExecutor` thread starts with an empty context, so a call it
makes records nowhere, and a page whose queries all run in parallel
showed "aito cached" though every query went to Aito.
"""

from concurrent.futures import ThreadPoolExecutor

from src import timing


def test_a_call_from_a_worker_thread_is_recorded_on_the_request():
    timing.start_request()

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [timing.submit_in_request(pool, timing.record_call, "/_relate", ms) for ms in (5.0, 7.0)]
        for job in jobs:
            job.result()

    assert sorted(timing.current_calls()) == [("_relate", 5.0), ("_relate", 7.0)]
