"""English pronunciation using installed Windows voices, with no network calls."""
import base64
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import wave


class SpeechUnavailable(Exception):
    pass


# This fixed program receives data as JSON over stdin. User text is never shell
# code or SSML; Speak(string) synthesizes plain text into an in-memory WAV.
SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($request.mode -eq 'voices') {
        $voices = @($synth.GetInstalledVoices() | Where-Object {
            $_.Enabled -and $_.VoiceInfo.Culture.Name.StartsWith('en-')
        } | ForEach-Object {
            @{name=$_.VoiceInfo.Name; culture=$_.VoiceInfo.Culture.Name}
        })
        [Console]::Write((ConvertTo-Json -InputObject $voices -Compress))
    } else {
        $synth.SelectVoice([string]$request.voice)
        $synth.Rate = [int]$request.rate
        $stream = New-Object System.IO.MemoryStream
        try {
            $synth.SetOutputToWaveStream($stream)
            $synth.Speak([string]$request.word)
            $synth.SetOutputToNull()
            $bytes = $stream.ToArray()
            $output = [Console]::OpenStandardOutput()
            $output.Write($bytes, 0, $bytes.Length)
            $output.Flush()
        } finally { $stream.Dispose() }
    }
} finally { $synth.Dispose() }
'''
ENCODED_SCRIPT = base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')
SYNTHESIS_SLOTS = threading.BoundedSemaphore(2)


def run_helper(payload):
    if sys.platform != 'win32':
        raise SpeechUnavailable('离线读音需要 Windows 本机英语语音。')
    executable = Path(os.environ.get('SystemRoot',r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        result = subprocess.run([str(executable),'-NoLogo','-NoProfile','-NonInteractive',
            '-EncodedCommand',ENCODED_SCRIPT], input=json.dumps(payload).encode('utf-8'),
            capture_output=True,timeout=25,creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise SpeechUnavailable('本机语音暂时无法启动，请稍后重试。') from exc
    if result.returncode:
        raise SpeechUnavailable('本机语音没有完成朗读，请确认 Windows 英语语音可用。')
    return result.stdout


@lru_cache(maxsize=1)
def installed_voices():
    try:
        voices=json.loads(run_helper({'mode':'voices'}).decode('utf-8-sig'))
        return tuple((v['name'],v['culture']) for v in voices
            if isinstance(v,dict) and isinstance(v.get('name'),str)
            and isinstance(v.get('culture'),str) and v['culture'].startswith('en-'))
    except (ValueError,TypeError,KeyError) as exc:
        raise SpeechUnavailable('无法读取本机英语语音，请重新打开应用。') from exc


def speech_status():
    try:
        voices=installed_voices()
    except SpeechUnavailable as exc:
        return {'available':False,'offline':True,'accents':[],'message':str(exc)}
    accents=[]
    for culture,label in [('en-US','美式英语'),('en-GB','英式英语')]:
        voice=next((name for name,locale in voices if locale==culture),None)
        if voice:accents.append({'id':culture,'label':label,'voice':voice})
    # Other installed English accents remain useful on machines without US/UK.
    for name,culture in voices:
        if not any(a['id']==culture for a in accents):
            accents.append({'id':culture,'label':f'英语（{culture}）','voice':name})
    return {'available':bool(accents),'offline':True,'accents':accents,
        'default':accents[0]['id'] if accents else None,
        'message':'本机合成语音 · 免费离线' if accents else 'Windows 未安装本地英语声音，请在系统语音设置中添加英语语音包。'}


def validate_word(word):
    if not isinstance(word,str):raise ValueError('请选择要朗读的英文单词。')
    word=' '.join(word.split())
    if not word or len(word)>120 or not re.search(r'[a-zA-Z]',word) or re.search(r"[^\w\s.'’\-]",word):
        raise ValueError('请输入不超过 120 字符的英文单词或短语。')
    return word


@lru_cache(maxsize=128)
def synthesize(word,voice,slow):
    with SYNTHESIS_SLOTS:
        audio=run_helper({'mode':'speak','word':word,'voice':voice,'rate':-3 if slow else 0})
    try:
        with wave.open(io.BytesIO(audio),'rb') as reader:
            if reader.getnframes()<1 or reader.getframerate()<8000:
                raise ValueError('Empty speech')
    except (wave.Error,EOFError,ValueError) as exc:
        raise SpeechUnavailable('本机语音未生成可播放的音频，请重试。') from exc
    return audio


def pronounce(data):
    word=validate_word(data.get('word'))
    accent=data.get('accent')
    slow=data.get('slow',False)
    if accent is not None and not isinstance(accent,str):raise ValueError('请选择读音口音。')
    if not isinstance(slow,bool):raise ValueError('慢速选项格式不正确。')
    status=speech_status()
    if not status['available']:raise SpeechUnavailable(status['message'])
    selected=next((a for a in status['accents'] if a['id']==(accent or status['default'])),None)
    if not selected:raise SpeechUnavailable('本机没有这个口音的离线声音，请在设置中选择已有声音。')
    return synthesize(word,selected['voice'],slow)
