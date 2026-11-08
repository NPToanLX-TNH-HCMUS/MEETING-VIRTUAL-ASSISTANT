# Benchmark Suite: PHASE 2 - Audio To Transcript

## 1. Overview
Evaluates speech-to-text accuracy and speaker diarization across multi-speaker meetings:
* Automatic Speech Recognition (ASR).
* Speaker segmentation & turn attribution.
* Timestamp alignment.

## 2. Dataset Specification (16 Cases Target)
* Source: AMI Meeting Corpus / Clean Studio Multi-speaker Recordings.
* Audio: 16kHz Mono PCM WAV.
* Target Cases:
  * `S01` - `S10`: Clean multi-speaker conversational meetings (30s - 60s).
  * `S11` - `S16`: Edge cases (rapid speech, cross-talk, acoustic hesitation, background noise).

## 3. Metrics
* Word Error Rate (WER <= 10% SLA): Levenshtein dynamic programming.
* Real-Time Factor (RTF <= 0.084) / Latency SLA (<= 5s for 60s audio).
* Speaker Diarization Accuracy (DER).

