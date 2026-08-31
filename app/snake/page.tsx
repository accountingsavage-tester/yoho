'use client'

import { useEffect, useRef, useState } from 'react'
import './snake.css'

const LYRICS = [
  'Litrato man natin ay kumupas',
  'Ikaw aking noon, ngayon, at bukas',
  "Kung paboritong kuwento nati'y magwakas",
  'Ay uulitin kong ikuwento bukas',
  'Sa pagdating ay siyang ating',
  'Buong pusong salubungin',
  "'Di man ngayon tulad ng dati",
  "Ang panata ko'y mananatili",
  'Kun ika man mapungaw',
  'Sa sakuyang paghali',
  'Dae makakalingaw',
  'Na ako mauli',
  'Kun ika man mahadit',
  'Na mapara ining ngirit',
  'Kada aldaw na ikinurit',
  'Pinili kang daing pirit',
  'Sa pag-abot kan panahon',
  'Sato ining aakuon',
  'Dawa ngunyan lain kan dati',
  "Ang panata ko'y mananatili",
  'Kaya tahan na',
  'Aking tahanan',
  'Kaya tahan na',
  'Aking tahanan',
]

const GRID = 21
const CELL = 20
const START_AT = 13
const LYRICS_DELAY = 700
const LYRIC_DURATION = 2800

export default function SnakePage() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const lyricTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const revealTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [started, setStarted] = useState(false)
  const [ended, setEnded] = useState(false)
  const [showLyrics, setShowLyrics] = useState(false)
  const [lyricIndex, setLyricIndex] = useState(0)
  const [score, setScore] = useState(0)

  useEffect(() => {
    const audio = audioRef.current
    if (audio) audio.src = '/Panata.mp3'
    return () => {
      if (lyricTimer.current) clearInterval(lyricTimer.current)
      if (revealTimer.current) clearTimeout(revealTimer.current)
    }
  }, [])

  useEffect(() => {
    if (!started) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    let snake = [{ x: 10, y: 10 }, { x: 9, y: 10 }, { x: 8, y: 10 }, { x: 7, y: 10 }]
    let food = { x: 15, y: 10 }
    let direction = { x: 1, y: 0 }
    let nextDirection = direction
    let running = true
    let timer: ReturnType<typeof setInterval>
    let currentScore = 0

    const placeFood = () => {
      do {
        food = { x: Math.floor(Math.random() * GRID), y: Math.floor(Math.random() * GRID) }
      } while (snake.some(q => q.x === food.x && q.y === food.y))
    }

    const draw = () => {
      ctx.fillStyle = '#000'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = '#f4df35'
      ctx.fillRect(food.x * CELL + 1, food.y * CELL + 1, CELL - 2, CELL - 2)
      snake.forEach((q, i) => {
        ctx.fillStyle = i === 0 ? '#8be9ff' : '#20b8d5'
        ctx.fillRect(q.x * CELL + 1, q.y * CELL + 1, CELL - 2, CELL - 2)
      })
    }

    const showMusicSequence = () => {
      const audio = audioRef.current
      if (lyricTimer.current) clearInterval(lyricTimer.current)
      if (revealTimer.current) clearTimeout(revealTimer.current)

      if (audio) {
        audio.pause()
        audio.currentTime = START_AT
        audio.play().catch(() => {})
      }

      revealTimer.current = setTimeout(() => {
        setShowLyrics(true)
        setLyricIndex(0)
        let i = 0
        lyricTimer.current = setInterval(() => {
          i += 1
          if (i >= LYRICS.length) {
            if (lyricTimer.current) clearInterval(lyricTimer.current)
            return
          }
          setLyricIndex(i)
        }, LYRIC_DURATION)
      }, LYRICS_DELAY)
    }

    const gameOver = () => {
      running = false
      clearInterval(timer)
      setEnded(true)
      setShowLyrics(false)
      setLyricIndex(0)
      revealTimer.current = setTimeout(showMusicSequence, 900)
    }

    const step = () => {
      if (!running) return
      direction = nextDirection
      const head = { x: snake[0].x + direction.x, y: snake[0].y + direction.y }
      const hitWall = head.x < 0 || head.x >= GRID || head.y < 0 || head.y >= GRID
      const hitSelf = snake.some((q, i) => i > 0 && q.x === head.x && q.y === head.y)
      if (hitWall || hitSelf) {
        gameOver()
        return
      }
      snake.unshift(head)
      if (head.x === food.x && head.y === food.y) {
        currentScore += 1
        setScore(currentScore)
        placeFood()
        clearInterval(timer)
        timer = setInterval(step, Math.max(55, 120 - currentScore * 2))
      } else {
        snake.pop()
      }
      draw()
    }

    const keyHandler = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase()
      if ((k === 'arrowup' || k === 'w') && direction.y !== 1) nextDirection = { x: 0, y: -1 }
      if ((k === 'arrowdown' || k === 's') && direction.y !== -1) nextDirection = { x: 0, y: 1 }
      if ((k === 'arrowleft' || k === 'a') && direction.x !== 1) nextDirection = { x: -1, y: 0 }
      if ((k === 'arrowright' || k === 'd') && direction.x !== -1) nextDirection = { x: 1, y: 0 }
    }

    window.addEventListener('keydown', keyHandler)
    placeFood()
    draw()
    timer = setInterval(step, 120)

    return () => {
      clearInterval(timer)
      window.removeEventListener('keydown', keyHandler)
    }
  }, [started])

  const begin = () => {
    if (lyricTimer.current) clearInterval(lyricTimer.current)
    if (revealTimer.current) clearTimeout(revealTimer.current)
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.currentTime = 0
    }
    setEnded(false)
    setShowLyrics(false)
    setLyricIndex(0)
    setScore(0)
    setStarted(false)
    setTimeout(() => setStarted(true), 20)
  }

  return (
    <main className={showLyrics ? 'party' : ''}>
      {!started && !ended && (
        <div className="start">
          <h1>SNAKE</h1>
          <button onClick={begin}>START GAME</button>
        </div>
      )}

      <section className="game">
        <header><span>SNAKE</span><b>{score}</b></header>
        <canvas ref={canvasRef} width={420} height={420} />
        <small>Arrow keys / WASD · Swipe on mobile</small>
      </section>

      <audio ref={audioRef} preload="auto" />

      {ended && !showLyrics && <div className="gameover">GAME OVER</div>}

      {showLyrics && (
        <>
          <div className="disco" aria-hidden="true">
            <i className="beam beam1" />
            <i className="beam beam2" />
            <i className="beam beam3" />
            <i className="beam beam4" />
          </div>
          <div className="lyrics" key={lyricIndex}>
            <div>♪ {LYRICS[lyricIndex]} ♪</div>
          </div>
        </>
      )}

      {ended && <button className="again" onClick={begin}>PLAY AGAIN</button>}
    </main>
  )
}
