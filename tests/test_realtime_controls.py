"""Offline checks: no physical microphone, network calls, or meeting data."""
import asyncio
import base64
import json
import unittest
from unittest.mock import patch

import numpy as np

from src.backend.speech_to_text import realtime_transcriber as rt


class RealtimeControlsTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, mode):
        stop = asyncio.Event()
        pause = asyncio.Event()
        paused_received = asyncio.Event()
        events, packets, streams = [], [], []

        class Microphone:
            def __init__(self, **kwargs):
                self.callback = kwargs['callback']
                self.active = False
                self.closed = False
                self.starts = 0
                streams.append(self)

            def start(self):
                self.active = True
                self.starts += 1
                block = np.full((rt.BLOCK_SIZE, 1), self.starts, dtype=np.int16)
                self.callback(block, len(block), None, type('Status', (), {'input_overflow': False})())

            def stop(self):
                self.active = False

            def __enter__(self):
                self.start()
                return self

            def __exit__(self, *args):
                self.stop()
                self.closed = True

        class Connection:
            def __init__(self):
                self.messages = asyncio.Queue()
                self.silences = 0
                self.closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                self.closed = True

            async def recv(self):
                return json.dumps({'message_type': 'session_started'})

            def __aiter__(self):
                return self

            async def __anext__(self):
                return await self.messages.get()

            async def send(self, raw):
                packet = json.loads(raw)
                pcm = base64.b64decode(packet['audio_base_64'])
                packets.append(packet)
                if packet['commit']:
                    await self.messages.put(json.dumps({
                        'message_type': 'committed_transcript', 'text': 'Retained transcript.',
                    }))
                elif pcm and any(pcm):
                    if streams[0].starts == 1:
                        pause.set()
                    else:
                        stop.set()
                else:
                    # During pause, hardware is stopped and only zeros go upstream.
                    self_test.assertFalse(streams[0].active)
                    self.silences += 1
                    if mode == 'resume' and self.silences == 2:
                        pause.clear()

        self_test = self
        connection = Connection()

        async def emit(event):
            events.append(event)
            if event['type'] == 'paused':
                self.assertFalse(streams[0].active)
                paused_received.set()
                if mode == 'stop_paused':
                    stop.set()

        with (
            patch.object(rt.sd, 'InputStream', Microphone),
            patch.object(rt, 'connect', return_value=connection),
            patch.object(rt, 'FINAL_WAIT_SECONDS', 0.02),
            patch.dict(rt.os.environ, {'ELEVENLABS_API_KEY': 'offline-test'}),
        ):
            task = asyncio.create_task(rt.stream_transcript(emit, stop_event=stop, pause_event=pause))
            if mode == 'disconnect':
                await asyncio.wait_for(paused_received.wait(), 2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            else:
                result = await asyncio.wait_for(task, 3)
                self.assertEqual(result, 'Retained transcript.')
                self.assertTrue(packets[-1]['commit'])

        self.assertTrue(streams[0].closed)
        self.assertTrue(connection.closed)
        self.assertFalse(streams[0].active)
        return [e['type'] for e in events], connection, streams[0]

    async def test_pause_sends_silence_and_resume_keeps_session(self):
        events, connection, microphone = await self.exercise('resume')
        self.assertEqual([e for e in events if e != 'level'][:3], ['ready', 'paused', 'resumed'])
        self.assertEqual(microphone.starts, 2)
        self.assertGreaterEqual(connection.silences, 2)

    async def test_stop_works_while_paused(self):
        events, _, microphone = await self.exercise('stop_paused')
        self.assertIn('stopping', events)
        self.assertNotIn('resumed', events)
        self.assertEqual(microphone.starts, 1)

    async def test_disconnect_during_pause_releases_microphone(self):
        await self.exercise('disconnect')
