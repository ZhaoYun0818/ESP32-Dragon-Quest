import network
import json
from microdot import Microdot
from microdot.websocket import with_websocket
import urandom
import utime
import uasyncio as asyncio
from machine import Pin, PWM, ADC, I2C
import gc
import ssd1306

oled = ssd1306.SSD1306_I2C(128, 64, I2C(0, scl=Pin(22), sda=Pin(21)))

# 設置 ESP32 為網路熱點
ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid='ESP32_勇者鬥惡龍')
ap.ifconfig(('192.168.4.1', '255.255.255.0', '192.168.4.1', '8.8.8.8'))
print('ESP32 熱點模式已啟動')
print('SSID: ESP32_勇者鬥惡龍')
print('IP 地址: 192.168.4.1')

# 蜂鳴器（GPIO 14）
buzzer = PWM(Pin(14, Pin.OUT))
buzzer.duty_u16(0)

# 搖桿（X: GPIO 35, Y: GPIO 32, 按鈕: GPIO 5）
adc_x = ADC(Pin(35))
adc_y = ADC(Pin(32))
button = Pin(17, Pin.IN, Pin.PULL_UP)
adc_x.atten(ADC.ATTN_11DB)
adc_y.atten(ADC.ATTN_11DB)

# 音效播放（非阻塞）
async def play_tone(freq, duration_ms):
    if freq == 0:
        buzzer.duty_u16(0)
    else:
        buzzer.freq(freq)
        buzzer.duty_u16(32768)
    await asyncio.sleep_ms(duration_ms)
    buzzer.duty_u16(0)

# 音效協程
async def sound_manager():
    global sound_queue
    while True:
        if sound_queue:
            sound_type = sound_queue.pop(0)
            if sound_type == 'hit':
                await play_tone(1000, 50)
            elif sound_type == 'win':
                for freq in [659, 784, 1047]:
                    await play_tone(freq, 100)
            elif sound_type == 'lose':
                for freq in [523, 392, 294]:
                    await play_tone(freq, 100)
        else:
            await asyncio.sleep_ms(10)

# 遊戲參數（高解析度）
PLAYER_WIDTH = 32
PLAYER_HEIGHT = 32
DRAGON_WIDTH = 64
DRAGON_HEIGHT = 64
FIREBALL_WIDTH = 16
FIREBALL_HEIGHT = 16
MAX_FIREBALLS = 3
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 640
GROUND_LEVEL = SCREEN_HEIGHT - PLAYER_HEIGHT - 32
tt=0
ttt=False
td=0

# 遊戲狀態
game_state = {
    'px': 40, 'py': GROUND_LEVEL, 'vy': 0, 'ong': True,
    'dx': 1360, 'dy': GROUND_LEVEL - DRAGON_HEIGHT + 32, 'da': True, 'dh': 5,
    'fb': [{'x': 0, 'y': 0, 'a': False} for _ in range(MAX_FIREBALLS)],
    'go': False, 'win': False, 'st': False,
    'lft': utime.ticks_ms(), 'mfb': MAX_FIREBALLS
}

# WebSocket 連接與音效隊列
connections = []
sound_queue = []
last_button_time = 0  # 按鈕防抖
frame_count = 0  # 垃圾回收計數

# 創建 Microdot 應用
app = Microdot()

# 重置遊戲
def reset_game():
    global game_state
    game_state = {
        'px': 40, 'py': GROUND_LEVEL, 'vy': 0, 'ong': True,
        'dx': 1360, 'dy': GROUND_LEVEL - DRAGON_HEIGHT + 32, 'da': True, 'dh': 5,
        'fb': [{'x': 0, 'y': 0, 'a': False} for _ in range(MAX_FIREBALLS)],
        'go': False, 'win': False, 'st': False,
        'lft': utime.ticks_ms(), 'mfb': MAX_FIREBALLS
    }

# 提供 HTML 頁面（全螢幕與高解析度）
@app.route('/')
async def index(request):
    return '''
<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>勇者鬥惡龍</title><style>body{margin:0;padding:0;background:#000;overflow:hidden}canvas{position:fixed;top:0;left:0;width:100vw;height:100vh;display:block;background:#000}@media (orientation:portrait){body::before{content:"請將設備旋轉至橫向";position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);color:#fff;font-size:2em;text-align:center;background:rgba(0,0,0,0.8);padding:20px;border-radius:10px;z-index:10}canvas{display:none}}</style></head><body><canvas id="c" width="1440" height="640"></canvas><script>const c=document.getElementById("c"),x=c.getContext("2d");function resizeCanvas(){const r=1440/640,wr=window.innerWidth,hr=window.innerHeight,cr=wr/hr;if(cr>r){c.style.width=`${hr*r}px`;c.style.height=`${hr}px`;}else{c.style.width=`${wr}px`;c.style.height=`${wr/r}px`;}c.style.left=`${(wr-c.offsetWidth)/2}px`;c.style.top=`${(hr-c.offsetHeight)/2}px`;}window.addEventListener("resize",resizeCanvas);resizeCanvas();const w=new WebSocket("ws://"+location.host+"/ws");w.onmessage=e=>{const d=JSON.parse(e.data);if(d.t=="u"){x.fillStyle="#000";x.fillRect(0,0,1440,640);if(!d.st){x.fillStyle="#fff";x.font="60px Arial";x.textAlign="center";x.fillText("按搖桿按鈕開始",720,320);return}x.fillStyle="#3498db";x.fillRect(0,608,1440,32);x.fillStyle="#0f0";x.fillRect(d.px,d.py,32,32);if(d.da){x.fillStyle=`rgb(${255-(5-d.dh)*51},${255-(5-d.dh)*51},${255-(5-d.dh)*51})`;x.fillRect(d.dx,d.dy,64,64)}x.fillStyle="#ffa500";d.fb.forEach(f=>f.a&&x.fillRect(f.x,f.y,16,16));if(d.go){x.fillStyle=d.win?"#0f0":"#f00";x.font="60px Arial";x.textAlign="center";x.fillText(d.win?"你贏了！按搖桿按鈕重新開始":"遊戲結束，按搖桿按鈕重新開始",720,320)}}}</script></body></html>
''', 200, {'Content-Type': 'text/html'}

# 遊戲迴圈
async def game_loop():
    global last_button_time, frame_count,tt,ttt,td
    while True:
        if frame_count % 5 == 0:
            gc.collect()  # 每 5 帧垃圾回收
        frame_count += 1

        if game_state['st'] and not game_state['go']:
            # 搖桿讀取（增強平滑）
            x_sum = 0
            y_sum = 0
            for _ in range(5):
                x_sum += adc_x.read_u16() >> 4
                y_sum += adc_y.read_u16() >> 4
                await asyncio.sleep_ms(1)
            x_val = x_sum // 5
            y_val = y_sum // 5
            button_val = button.value()

            # 搖桿控制
            left = x_val < 1000
            right = x_val > 3000
            jump = y_val < 1000
            if left:
                game_state['px'] = max(0, game_state['px'] - 8)
            if right:
                game_state['px'] = min(SCREEN_WIDTH - PLAYER_WIDTH, game_state['px'] + 8)
            if jump and game_state['ong']:
                game_state['vy'] = -20
                game_state['ong'] = False

            # 重力
            game_state['py'] += game_state['vy']
            game_state['vy'] += 2
            if game_state['py'] >= GROUND_LEVEL:
                game_state['py'] = GROUND_LEVEL
                game_state['vy'] = 0
                game_state['ong'] = True

            # 火球生成
            if game_state['dh'] > 0:
                ct = utime.ticks_ms()
                if utime.ticks_diff(ct, game_state['lft']) >= urandom.randint(567 + game_state['dh'] * 123, (game_state['dh'] + 1) * 555): #火球生成間隔
                    for fb in game_state['fb']:
                        if not fb['a']:
                            fb['x'] = game_state['dx'] - FIREBALL_WIDTH
                            if game_state['dh'] <=2: #火球高度
                                fb['y'] = game_state['dy'] + DRAGON_HEIGHT // 2+urandom.randint(-30*(3-game_state['dh']),25)
                            else:
                                fb['y'] = game_state['dy'] + DRAGON_HEIGHT // 2
                            fb['a'] = True
                            game_state['lft'] = ct
                            break

            # 火球更新
            for fb in game_state['fb']:
                if fb['a']:
                    fb['x'] -= 10 + (7 - game_state['dh']) #火球速度
                    if fb['x'] < -FIREBALL_WIDTH:
                        fb['a'] = False

            # 碰撞檢測
            if game_state['da'] and game_state['dh'] > 0:
                if (game_state['px'] + PLAYER_WIDTH > game_state['dx'] and
                    game_state['px'] < game_state['dx'] + DRAGON_WIDTH and
                    game_state['py'] + PLAYER_HEIGHT > game_state['dy'] and
                    game_state['py'] < game_state['dy'] + DRAGON_HEIGHT):
                    game_state['dh'] -= 1
                    if game_state['dh'] <= 0:
                        ttt=False
                        game_state['da'] = False
                        game_state['win'] = True
                        game_state['go'] = True
                        sound_queue.append('win')
                    else:
                        game_state['px'] = 40
                        game_state['py'] = GROUND_LEVEL
                        game_state['vy'] = 0
                        game_state['ong'] = True
                        game_state['mfb'] += game_state['dh'] //2 #火球數量
                        game_state['fb'] = [{'x': 0, 'y': 0, 'a': False} for _ in range(game_state['mfb'])]
                        sound_queue.append('hit')

            for fb in game_state['fb']:
                if fb['a']:
                    if (game_state['px'] + PLAYER_WIDTH > fb['x'] and
                        game_state['px'] < fb['x'] + FIREBALL_WIDTH and
                        game_state['py'] + PLAYER_HEIGHT > fb['y'] and
                        game_state['py'] < fb['y'] + FIREBALL_HEIGHT):
                        ttt=False
                        game_state['go'] = True
                        game_state['win'] = False
                        sound_queue.append('lose')

        # 按鈕控制（防抖）
        button_val = button.value()
        if button_val == 0 and utime.ticks_diff(utime.ticks_ms(), last_button_time) > 150:
            tt=utime.time()
            ttt=True
            if not game_state['st']:
                game_state['st'] = True
            elif game_state['go']:
                reset_game()
                game_state['st'] = True
            last_button_time = utime.ticks_ms()

        # 廣播
        await broadcast({
            't': 'u',
            'px': game_state['px'], 'py': game_state['py'],
            'dx': game_state['dx'], 'dy': game_state['dy'], 'da': game_state['da'], 'dh': game_state['dh'],
            'fb': game_state['fb'],
            'go': game_state['go'], 'win': game_state['win'], 'st': game_state['st']
        })
        
        if ttt == True and (utime.time()-tt)%60!=td:
            oled.fill(0)
            oled.text(str((utime.time()-tt)//60)+':'+str((utime.time()-tt)%60), 10, 0)
            oled.show()
            td=(utime.time()-tt)%60
        
        await asyncio.sleep_ms(16)  # 40 FPS

# WebSocket 路由
@app.route('/ws')
@with_websocket
async def websocket(request, ws):
    try:
        connections.append(ws)
        if len(connections) > 1:
            await ws.send(json.dumps({'t': 'e', 'm': '僅支援一名玩家'}))
            return

        await ws.send(json.dumps({
            't': 'u',
            'px': game_state['px'], 'py': game_state['py'],
            'dx': game_state['dx'], 'dy': game_state['dy'], 'da': game_state['da'], 'dh': game_state['dh'],
            'fb': game_state['fb'],
            'go': game_state['go'], 'win': game_state['win'], 'st': game_state['st']
        }))

        while True:
            try:
                data = await ws.receive()
                if not data:
                    break
            except Exception as e:
                print('WebSocket 錯誤:', e)
                break
    finally:
        connections.remove(ws)

# 廣播
async def broadcast(msg):
    for conn in connections[:]:
        try:
            await conn.send(json.dumps(msg))
        except:
            connections.remove(conn)

# 主程式
async def main():
    asyncio.create_task(sound_manager())
    asyncio.create_task(game_loop())
    try:
        app.run(port=80)
    except Exception as e:
        print('服務器錯誤:', e)
    finally:
        buzzer.duty_u16(0)
        buzzer.deinit()

# 運行
try:
    gc.collect()
    asyncio.run(main())
except KeyboardInterrupt:
    buzzer.duty_u16(0)
    buzzer.deinit()
