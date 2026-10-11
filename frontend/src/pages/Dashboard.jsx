// frontend/src/pages/Dashboard.jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import CameraFeed from '../components/CameraFeed'
import AlertBanner from '../components/AlertBanner'
import DetectionList from '../components/DetectionList'
import { LANGUAGES } from '../languages.js'
import { apiRequest, fetchSpeechAudioUrl, getHistory, getStats } from '../services/api.js'
import '../App.css'

const SPEECH_RATE = 1.22

export default function Dashboard() {
  const { user, logout } = useAuth()

  const [running, setRunning] = useState(false)
  const [voice, setVoice] = useState(true)
  const [battery, setBattery] = useState(null)
  const [batteryError, setBatteryError] = useState('')
  const [location, setLocation] = useState(null)
  const [isListening, setIsListening] = useState(false)
  const [currentDetections, setCurrentDetections] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')
  const [speechStatus, setSpeechStatus] = useState('')
  const [language, setLanguage] = useState(() => {
    const savedLanguage = localStorage.getItem('aod_lang')
    return LANGUAGES.some((item) => item.code === savedLanguage) ? savedLanguage : 'en'
  })

  const lastSpoken = useRef({ text: '', language: '', time: 0 })
  const audioRef = useRef(null)
  const audioUrlRef = useRef(null)
  const playbackGenerationRef = useRef(0)
  const recognitionRef = useRef(null)
  const recognitionGenerationRef = useRef(0)
  const listeningRequestedRef = useRef(false)

  useEffect(() => {
    localStorage.setItem('aod_lang', language)
  }, [language])

  useEffect(() => {
    let isActive = true

    const fetchBattery = async () => {
      try {
        const data = await apiRequest('/battery')
        if (isActive) {
          setBattery(data)
          setBatteryError('')
        }
      } catch (err) {
        if (isActive) {
          setBatteryError(err.message || 'Battery status could not be loaded.')
        }
      }
    }

    fetchBattery()
    const interval = window.setInterval(fetchBattery, 60000)
    return () => {
      isActive = false
      window.clearInterval(interval)
    }
  }, [])

  useEffect(
    () => () => {
      recognitionGenerationRef.current += 1
      listeningRequestedRef.current = false
      recognitionRef.current?.stop()
      recognitionRef.current = null
    },
    [],
  )

  useEffect(() => {
    if (!('speechSynthesis' in window)) return undefined

    const syncVoices = () => {
      const voices = window.speechSynthesis.getVoices()
      if (voices.length > 0) {
        console.log('🔊 browser voices loaded:', voices.length)
      }
    }

    syncVoices()
    if ('onvoiceschanged' in window.speechSynthesis) {
      window.speechSynthesis.onvoiceschanged = syncVoices
    }

    return () => {
      if ('onvoiceschanged' in window.speechSynthesis) {
        window.speechSynthesis.onvoiceschanged = null
      }
    }
  }, [])

  const stopSpeech = useCallback(() => {
    playbackGenerationRef.current += 1
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.removeAttribute('src')
      audioRef.current.load()
      audioRef.current = null
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current)
      audioUrlRef.current = null
    }
  }, [])

  useEffect(() => stopSpeech, [stopSpeech])

  const speak = useCallback(
    (text) => {
      if (!voice || !text) return

      const now = Date.now()
      if (
        text === lastSpoken.current.text &&
        language === lastSpoken.current.language &&
        now - lastSpoken.current.time < 3000
      ) {
        return
      }
      lastSpoken.current = { text, language, time: now }

      stopSpeech()
      const playbackGeneration = playbackGenerationRef.current

      const langConfig = LANGUAGES.find((item) => item.code === language)
      const ttsLocale = langConfig?.tts || 'en-US'
      const langPrefix = ttsLocale.split('-')[0].toLowerCase()
      const voices =
        'speechSynthesis' in window ? window.speechSynthesis.getVoices() : []
      const hasNativeVoice = voices.some((availableVoice) =>
        availableVoice.lang.toLowerCase().startsWith(langPrefix),
      )
      const matchingVoice =
        voices.find(
          (availableVoice) =>
            availableVoice.lang.toLowerCase() === ttsLocale.toLowerCase(),
        ) ||
        voices.find((availableVoice) =>
          availableVoice.lang.toLowerCase().startsWith(langPrefix),
        ) ||
        voices.find((availableVoice) =>
          availableVoice.lang.toLowerCase().startsWith('en'),
        ) ||
        voices[0]

      const speakWithBrowser = (speechText, locale, voiceOption, statusMessage) => {
        if (!('speechSynthesis' in window)) return false
        const utterance = new SpeechSynthesisUtterance(speechText)
        utterance.lang = voiceOption?.lang || locale
        if (voiceOption) utterance.voice = voiceOption
        utterance.rate = SPEECH_RATE
        utterance.volume = 1.0
        utterance.onstart = () =>
          setSpeechStatus(statusMessage || 'Speaking with browser voice...')
        utterance.onend = () => setSpeechStatus('Speech finished.')
        utterance.onerror = (event) => {
          if (event.error === 'interrupted' || event.error === 'canceled') return
          console.error('Speech error:', event.error)
          setSpeechStatus(`Speech failed: ${event.error}`)
        }
        window.speechSynthesis.speak(utterance)
        return true
      }

      if (language === 'en') {
        if (speakWithBrowser(text, ttsLocale, matchingVoice)) {
          console.log(`🔊 Browser TTS (${language})`)
          return
        }
      }

      const chunks = text.match(/.{1,190}/g) || [text]
      const providerName = (provider) =>
        provider === 'local-mms' ? 'local TTS' : 'Google TTS'
      const localSpeechUnavailable = ['ti', 'om', 'so'].includes(language)
      const playChunk = async (index) => {
        if (playbackGeneration !== playbackGenerationRef.current) return
        if (index >= chunks.length) {
          setSpeechStatus('Speech finished.')
          console.log(`✅ TTS finished (${language})`)
          return
        }
        let audioResult
        try {
          audioResult = await fetchSpeechAudioUrl(chunks[index], language)
        } catch (error) {
          if (playbackGeneration !== playbackGenerationRef.current) return
          console.error(`❌ TTS failed for "${language}":`, error)
          if (localSpeechUnavailable) {
            setSpeechStatus(error.message || `Local speech unavailable for ${language}.`)
            return
          }
          const isUnsupported = error.message.includes('does not support language')
          const fallbackVoice = hasNativeVoice ? matchingVoice : undefined
          const fallbackLocale = fallbackVoice?.lang || 'en-US'
          const fallbackMessage = isUnsupported
            ? `Google TTS does not support ${language}; using ${fallbackLocale} browser voice.`
            : `Google TTS unavailable; using ${fallbackLocale} browser voice.`
          setSpeechStatus(fallbackMessage)
          if (!speakWithBrowser(text, fallbackLocale, fallbackVoice, fallbackMessage)) {
            setSpeechStatus(error.message || 'Speech is unavailable in this browser.')
          }
          return
        }

        const { url: audioUrl, provider } = audioResult
        const providerLabel = providerName(provider)
        if (playbackGeneration !== playbackGenerationRef.current) {
          URL.revokeObjectURL(audioUrl)
          return
        }

        const audio = new Audio(audioUrl)
        audio.volume = 1.0
        audio.playbackRate = SPEECH_RATE
        audioRef.current = audio
        audioUrlRef.current = audioUrl
        audio.onplay = () => setSpeechStatus(`Speaking with ${providerLabel} (${language})...`)
        audio.onended = () => {
          if (audioRef.current !== audio) return
          audioRef.current = null
          URL.revokeObjectURL(audioUrl)
          audioUrlRef.current = null
          playChunk(index + 1)
        }
        audio.onerror = () => {
          if (audioRef.current !== audio) return
          audioRef.current = null
          URL.revokeObjectURL(audioUrl)
          audioUrlRef.current = null
          console.error(`❌ ${providerLabel} playback failed for "${language}"`)
          if (localSpeechUnavailable) {
            setSpeechStatus(`Local speech playback failed for ${language}.`)
            return
          }
          const fallbackVoice = hasNativeVoice ? matchingVoice : undefined
          const fallbackLocale = fallbackVoice?.lang || 'en-US'
          const fallbackMessage =
            `Google TTS unavailable; using ${fallbackLocale} browser voice.`
          setSpeechStatus(fallbackMessage)
          if (!speakWithBrowser(text, fallbackLocale, fallbackVoice, fallbackMessage)) {
            setSpeechStatus('Speech is unavailable in this browser.')
          }
        }
        audio.play().catch((error) => {
          if (audioRef.current !== audio) return
          audioRef.current = null
          URL.revokeObjectURL(audioUrl)
          audioUrlRef.current = null
          console.error(`❌ ${providerLabel} playback failed:`, error)
          if (localSpeechUnavailable) {
            setSpeechStatus(`Local speech playback failed for ${language}.`)
            return
          }
          const fallbackVoice = hasNativeVoice ? matchingVoice : undefined
          const fallbackLocale = fallbackVoice?.lang || 'en-US'
          const fallbackMessage =
            `Google TTS playback failed; using ${fallbackLocale} browser voice.`
          setSpeechStatus(fallbackMessage)
          if (!speakWithBrowser(text, fallbackLocale, fallbackVoice, fallbackMessage)) {
            setSpeechStatus('Speech is unavailable in this browser.')
          }
        })
      }

      setSpeechStatus(`Starting speech (${language})...`)
      playChunk(0)
    },
    [language, voice, stopSpeech],
  )

  const testVoice = useCallback(() => {
    console.log('🔊 Test voice — language:', language)
    const samples = {
      en: 'Test voice. One, two, three.',
      am: 'የድምፅ ሙከራ። አንድ፣ ሁለት፣ ሶስት።',
      ti: 'ናይ ድምፂ ፈተነ።',
      om: 'Qorannoo sagalee.',
      so: 'Tijaabada codka.',
      ar: 'اختبار الصوت. واحد، اثنان، ثلاثة.',
      es: 'Prueba de voz. Uno, dos, tres.',
      fr: 'Test vocal. Un, deux, trois.',
      de: 'Stimmentest. Eins, zwei, drei.',
      it: 'Prova vocale. Uno, due, tre.',
      pt: 'Teste de voz. Um, dois, três.',
      ru: 'Проверка голоса.',
      zh: '语音测试。一二三。',
      ja: 'ボイステスト。',
      ko: '음성 테스트.',
      hi: 'आवाज परीक्षण।',
      sw: 'Jaribio la sauti.',
      tr: 'Ses testi.',
      vi: 'Kiểm tra giọng nói.',
      id: 'Tes suara.',
      ur: 'آواز کی جانچ۔',
      fa: 'تست صدا.',
      he: 'בדיקת קול.',
      pl: 'Test głosu.',
      nl: 'Stemtest.',
      uk: 'Перевірка голосу.',
    }
    const text = samples[language] || samples.en
    stopSpeech()
    setSpeechStatus('Starting voice test...')
    lastSpoken.current = { text: '', language: '', time: 0 }
    speak(text)
  }, [language, speak, stopSpeech])

  const loadData = useCallback(async () => {
    try {
      const [h, s] = await Promise.all([getHistory(10), getStats()])
      setHistory(h)
      setStats(s)
    } catch (err) {
      console.log('History/stats not loaded:', err.message)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleResult = useCallback(
    (result) => {
      setError('')
      setCurrentDetections(result.detections || [])
      if (result.message) {
        speak(result.message)
      } else if (voice) {
        setSpeechStatus('No urgent object detected; waiting...')
      }
      setTimeout(loadData, 500)
    },
    [speak, loadData, voice],
  )

  const handleError = useCallback((msg) => {
    setError(msg || 'Something went wrong')
    setRunning(false)
  }, [])

  function toggleRunning() {
    setError('')
    setSpeechStatus('')
    if (running) {
      setCurrentDetections([])
      stopSpeech()
    }
    setRunning((r) => !r)
  }

  async function toggleListening() {
    if (listeningRequestedRef.current) {
      recognitionGenerationRef.current += 1
      listeningRequestedRef.current = false
      recognitionRef.current?.stop()
      recognitionRef.current = null
      setIsListening(false)
      setSpeechStatus('Listening stopped.')
      return
    }

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setSpeechStatus('Voice input is not supported in this browser.')
      return
    }

    const generation = ++recognitionGenerationRef.current
    listeningRequestedRef.current = true
    setIsListening(true)

    const prepareLocalRecognition = async (targetLocale) => {
      if (
        typeof SpeechRecognition.available !== 'function' ||
        typeof SpeechRecognition.install !== 'function'
      ) {
        return false
      }

      try {
        let availability = await SpeechRecognition.available({
          langs: [targetLocale],
          processLocally: true,
        })

        if (availability === 'downloadable' || availability === 'downloading') {
          setSpeechStatus(`Preparing offline voice input for ${targetLocale}...`)
          const installed = await SpeechRecognition.install({
            langs: [targetLocale],
          })
          if (!installed) return false
          availability = await SpeechRecognition.available({
            langs: [targetLocale],
            processLocally: true,
          })
        }

        return availability === 'available'
      } catch (err) {
        console.warn(
          `On-device speech recognition is unavailable for ${targetLocale}:`,
          err,
        )
        return false
      }
    }

    const startRecognition = async (
      locale,
      retryWithEnglish,
      retryOnline = false,
    ) => {
      const processLocally = retryOnline
        ? false
        : await prepareLocalRecognition(locale)
      if (generation !== recognitionGenerationRef.current) return

      if (processLocally) {
        setSpeechStatus(`Listening privately on this device in ${locale}...`)
      } else if (typeof SpeechRecognition.available === 'function') {
        setSpeechStatus(
          `On-device voice input is unavailable for ${locale}; trying browser speech recognition...`,
        )
      }

      let recognition
      let shouldRetryWithEnglish = false
      let shouldRetryOnline = false
      const embeddedBrowser = /Electron\//i.test(navigator.userAgent)
      try {
        recognition = new SpeechRecognition()
        recognition.lang = locale
        if (processLocally && 'processLocally' in recognition) {
          recognition.processLocally = true
        }
        recognition.onresult = (event) => {
          const transcript = event.results?.[0]?.[0]?.transcript
          if (transcript) {
            setSpeechStatus(`Heard: ${transcript}`)
            speak(`You said: ${transcript}`)
          }
        }
        recognition.onerror = (event) => {
          if (
            event.error === 'network' &&
            retryWithEnglish &&
            locale.toLowerCase() !== 'en-us'
          ) {
            shouldRetryWithEnglish = true
            setSpeechStatus(
              `Speech service unavailable for ${locale}; retrying voice input in English.`,
            )
            return
          }

          if (
            processLocally &&
            ['language-not-supported', 'service-not-allowed'].includes(event.error)
          ) {
            shouldRetryOnline = true
            setSpeechStatus(
              `Offline voice input is unavailable for ${locale}; trying the browser speech service.`,
            )
            return
          }

          const errorMessages = {
            network: embeddedBrowser
              ? 'Voice recognition is unavailable in this VS Code preview. Open this page in Chrome or Edge, allow microphone access, and tap Listen again.'
              : 'Voice recognition could not connect. Check your internet connection, allow microphone access, and tap Listen to retry.',
            'not-allowed':
              'Microphone access was blocked. Allow microphone access for this site and try again.',
            'audio-capture':
              'No microphone is available. Connect or enable a microphone, then try again.',
            'no-speech': 'No speech was detected. Try speaking closer to the microphone.',
          }
          setSpeechStatus(
            errorMessages[event.error] || `Voice input error: ${event.error}`,
          )
        }
        recognition.onend = () => {
          if (recognitionRef.current !== recognition) return
          if (shouldRetryWithEnglish) {
            void startRecognition('en-US', false)
            return
          }
          if (shouldRetryOnline) {
            void startRecognition(locale, retryWithEnglish, true)
            return
          }
          recognitionRef.current = null
          listeningRequestedRef.current = false
          setIsListening(false)
        }
        recognition.onstart = () => {
          setIsListening(true)
          if (!processLocally) {
            setSpeechStatus(
              locale === 'en-US' && retryWithEnglish === false
                ? 'Listening in English (fallback)...'
                : `Listening in ${locale}...`,
            )
          }
        }
        recognitionRef.current = recognition
        recognition.start()
      } catch (err) {
        if (generation !== recognitionGenerationRef.current) return
        if (recognitionRef.current === recognition) recognitionRef.current = null
        listeningRequestedRef.current = false
        setIsListening(false)
        setSpeechStatus(`Could not start voice input: ${err.message}`)
      }
    }

    const locale = LANGUAGES.find((item) => item.code === language)?.tts || 'en-US'
    await startRecognition(locale, true)
  }

  function handleGetLocation() {
    if (!navigator.geolocation) {
      setSpeechStatus('Location is not supported in this browser.')
      return
    }

    setSpeechStatus('Getting your location...')
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const latitude = Number(position.coords.latitude.toFixed(4))
        const longitude = Number(position.coords.longitude.toFixed(4))
        const coordinates = {
          latitude,
          longitude,
        }
        setSpeechStatus('Looking up your nearby place...')
        try {
          const result = await apiRequest(
          `/location/reverse?latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}&language=${encodeURIComponent(LANGUAGES.find((item) => item.code === language)?.tts || 'en-US')}`,
          )
          setLocation({ ...coordinates, address: result.address })
          speak(
            `${result.description} Coordinates: latitude ${latitude}, longitude ${longitude}.`,
          )
        } catch (err) {
          setLocation(coordinates)
          setSpeechStatus(
            `Place lookup failed: ${err.message}. I can still give your coordinates.`,
          )
          speak(
            `Place name unavailable. Your coordinates are latitude ${latitude}, longitude ${longitude}.`,
          )
        }
      },
      (err) => {
        setSpeechStatus(`Location error: ${err.message}`)
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    )
  }

  async function handleLogout() {
    if (running) {
      setRunning(false)
      stopSpeech()
    }
    logout()
  }

  const byDanger = stats?.by_danger_level || {}
  const latest = history.length > 0 ? history[0].label : 'None yet'

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <div className="header-titles">
          <h1 className="project-title">
            AI-Based Real-Time Object and Obstacle Detection System
          </h1>
          <p className="project-subtitle">
            For Visually Impaired People
          </p>
          <p className="welcome-user">
            👤 Welcome, <strong>{user?.name || 'User'}</strong>
          </p>
        </div>

        <div className="header-controls">
          <select
            className="language-select"
            value={language}
            onChange={(event) => setLanguage(event.target.value)}
            title="Alert language"
            aria-label="Alert language"
          >
            {LANGUAGES.map((item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
          <button className="btn-logout" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      {error && <div className="alert alert-danger">{error}</div>}

      {running && <AlertBanner detections={currentDetections} />}

      <div className="stats-grid">
        <div className="stat-card">
          <p className="stat-label">Total detections</p>
          <p className="stat-value">{stats?.total ?? 0}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Latest</p>
          <p className="stat-value">{latest}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">By danger level</p>
          <p className="stat-value">
            danger: {byDanger.danger ?? 0}, safe: {byDanger.safe ?? 0}, warning:{' '}
            {byDanger.warning ?? 0}
          </p>
        </div>
      </div>

      <section className="live-section">
        <div className="live-header">
          <h2>Live Detection</h2>
          <div className="live-controls">
            <button
              className={`btn ${running ? 'btn-danger' : 'btn-success'}`}
              onClick={toggleRunning}
              type="button"
            >
              {running ? '⏹ Stop' : '▶ Start Detection'}
            </button>
            <button
              className="btn btn-voice-input"
              onClick={toggleListening}
              disabled={!voice && !isListening}
              type="button"
            >
              {isListening ? '⏹ Stop listening' : '🎤 Listen'}
            </button>
            <button
              className="btn btn-location"
              onClick={handleGetLocation}
              type="button"
            >
              📍 Location
            </button>
            {battery?.available ? (
              <span className="battery-badge" role="status">
                🔋 {battery.percent}% {battery.plugged ? '⚡' : ''}
              </span>
            ) : battery && !battery.available ? (
              <span className="battery-badge battery-unavailable" role="status">
                🔋 Battery unavailable
              </span>
            ) : batteryError ? (
              <span className="battery-badge battery-unavailable" role="status">
                🔋 {batteryError}
              </span>
            ) : null}
            <label className="voice-toggle">
              <input
                type="checkbox"
                checked={voice}
                onChange={(e) => setVoice(e.target.checked)}
              />
              Voice
            </label>
            <button
              className="btn btn-voice-test"
              type="button"
              onClick={testVoice}
              disabled={!voice}
            >
              Test voice
            </button>
            {speechStatus && (
              <span className="voice-status" role="status">
                {speechStatus}
              </span>
            )}
            {location && (
              <span className="location-status" role="status">
                📍 {location.address ? `${location.address} (${location.latitude}, ${location.longitude})` : `${location.latitude}, ${location.longitude}`}
              </span>
            )}
          </div>
        </div>

        <div className="live-grid">
          <div className="camera-wrapper">
            <CameraFeed
              running={running}
              language={language}
              onResult={handleResult}
              onError={handleError}
            />
          </div>

          <div className="live-side">
            <h3>Detected now</h3>
            <DetectionList detections={currentDetections} />
          </div>
        </div>
      </section>

      <section className="history-section">
        <h2>Recent detections</h2>
        {history.length === 0 ? (
          <p className="muted">No detections yet.</p>
        ) : (
          <ul className="history-list">
            {history.map((h) => (
              <li key={h.id} className="history-item">
                <span className="history-label">{h.label}</span>
                <span className="history-confidence">
                  {h.confidence.toFixed(2)} confidence
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}