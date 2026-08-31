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

export default function SnakePage() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const [started, setStarted] = useState(false)
  const [ended, setEnded] = useState(false)
  const [showLyrics, setShowLyrics] = useState(false)
  const [lyricIndex, setLyricIndex] = useState(0)
  const [score, setScore] = useState(0)
  const audioUrl = useRef<string | null>(null)

  useEffect(() => {
    fetch('/panata.b64').then(r=>r.text()).then(b64=>{
      const raw=atob(b64.trim()); const bytes=new Uint8Array(raw.length)
      for(let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i)
      const blob=new Blob([bytes],{type:'audio/mpeg'})
      audioUrl.current=URL.createObjectURL(blob)
      if(audioRef.current) audioRef.current.src=audioUrl.current
    }).catch(()=>{})
    return()=>{if(audioUrl.current) URL.revokeObjectURL(audioUrl.current)}
  },[])

  useEffect(() => {
    if (!started) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const N = 21, z = canvas.width / N
    let snake = [{x:10,y:10},{x:9,y:10},{x:8,y:10},{x:7,y:10}]
    let food = {x:15,y:10}, running = true
    let timer: ReturnType<typeof setInterval>
    let currentScore = 0
    const placeFood = () => { do food={x:Math.floor(Math.random()*N),y:Math.floor(Math.random()*N)}; while(snake.some(q=>q.x===food.x&&q.y===food.y)) }
    const draw = () => { ctx.fillStyle='#000';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#f4df35';ctx.fillRect(food.x*z+1,food.y*z+1,z-2,z-2);snake.forEach((q,i)=>{ctx.fillStyle=i?'#20b8d5':'#62d9ee';ctx.fillRect(q.x*z+1,q.y*z+1,z-2,z-2)}) }
    const over = () => {
      running=false; clearInterval(timer); setEnded(true)
      const audio=audioRef.current
      if(audio){ audio.currentTime=0; audio.play().catch(()=>{}) }
      setTimeout(()=>{ if(audio){ audio.currentTime=0; audio.play().catch(()=>{}) }; setShowLyrics(true) },900)
      let i=0; setLyricIndex(0)
      const lt=setInterval(()=>{i++;if(i>=LYRICS.length){clearInterval(lt);return}setLyricIndex(i)},3000)
    }
    const step = () => { if(!running)return; const d=(window as any).__snakeDir||{x:1,y:0}; const h={x:snake[0].x+d.x,y:snake[0].y+d.y}; if(h.x<0||h.x>=N||h.y<0||h.y>=N||snake.some((q,i)=>i&&q.x===h.x&&q.y===h.y)){over();return} snake.unshift(h);if(h.x===food.x&&h.y===food.y){currentScore++;setScore(currentScore);placeFood();clearInterval(timer);timer=setInterval(step,Math.max(55,120-currentScore*2))}else snake.pop();draw() }
    const key=(e:KeyboardEvent)=>{let k=e.key.toLowerCase(),d=(window as any).__snakeDir||{x:1,y:0};if((k==='arrowup'||k==='w')&&d.y!==1)(window as any).__snakeDir={x:0,y:-1};if((k==='arrowdown'||k==='s')&&d.y!==-1)(window as any).__snakeDir={x:0,y:1};if((k==='arrowleft'||k==='a')&&d.x!==1)(window as any).__snakeDir={x:-1,y:0};if((k==='arrowright'||k==='d')&&d.x!==-1)(window as any).__snakeDir={x:1,y:0}}
    ;(window as any).__snakeDir={x:1,y:0}; addEventListener('keydown',key); placeFood(); draw(); timer=setInterval(step,120)
    return()=>{clearInterval(timer);removeEventListener('keydown',key)}
  },[started])

  const begin=()=>{setEnded(false);setShowLyrics(false);setLyricIndex(0);setScore(0);setStarted(false);setTimeout(()=>setStarted(true),20)}
  return <main className={showLyrics?'party':''}>
    {!started && !ended && <div className="start"><h1>SNAKE</h1><button onClick={begin}>START GAME</button></div>}
    <section className="game"><header><span>SNAKE</span><b>{score}</b></header><canvas ref={canvasRef} width={420} height={420}/><small>Arrow keys / WASD · Swipe on mobile</small></section>
    <audio ref={audioRef} preload="auto" />
    {ended && !showLyrics && <div className="gameover">GAME OVER</div>}
    {showLyrics && <><div className="disco"/><div className="lyrics"><div>♪ {LYRICS[lyricIndex]} ♪</div></div></>}
    {ended && <button className="again" onClick={begin}>PLAY AGAIN</button>}
  </main>
}
