import os
import sys
import random
import pygame as pg
import math


# =========================
# 基本設定・定数
# =========================
WIDTH = 1100     # 画面幅
HEIGHT = 650     # 画面高さ
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # fig参照のため

FPS = 60

# プレイヤーが立つ床の高さ（床の上面のY座標）
GROUND_Y = 520

# 色（スコア文字など）
TEXT_COLOR = (10, 10, 10)

# 床ブロックの色
BLOCK_MAIN = (180, 120, 40)   # ブロックの茶色い面
BLOCK_EDGE = (110, 70, 20)    # ブロックのふち色（こげ茶）

# 物理系
GRAVITY = 1.0         # 重力(下向き加速度)
JUMP_VELOCITY = -22   # ジャンプ初速（マイナスで上方向）
BOUNCE_VELOCITY = -12 # 踏みつぶした後の小さいバウンド

# プレイヤーのサイズ
CAR_W = 100
CAR_H = 60

# 障害物スポーン関係
SPAWN_INTERVAL_MS = 1100      # 障害物出現間隔（ミリ秒）
SPEED_START = 8.0             # 最初のスクロール速度
SPEED_ACCEL = 0.05            # 時間がたつと速くなる係数（どんどん速くなる）

# スコア系
STOMP_SCORE = 100             # 踏みつぶし時に入るスコア

# ゲームオーバー後に自動終了するまでの待ち時間（ミリ秒）
GAMEOVER_EXIT_DELAY_MS = 5000

# アイテム関係
STAR_DURATION_MS = 4000       # スター効果持続時間（ミリ秒）
STAR_SPAWN_INTERVAL_MS = 8000 # スター出現間隔（ミリ秒）
STAR_BLINK_INTERVAL = 5       # 点滅間隔（フレーム）


def draw_text(surface: pg.Surface,
              text: str,
              font: pg.font.Font,
              x: int,
              y: int,
              color: tuple[int, int, int] = TEXT_COLOR):
    """左上基準でテキスト描画"""
    img = font.render(text, True, color)
    surface.blit(img, (x, y))


def draw_bg_scroll(surface: pg.Surface,
                   img_a: pg.Surface,
                   img_b: pg.Surface,
                   scroll_x: float):
    """
    背景を横スクロールでループ表示する。
    img_a と img_b(左右反転) を A|B|A|B|... でつなぐ。
    """
    w = img_a.get_width()
    pair_w = w * 2  # [A|B] セットの幅

    start_x = int(scroll_x) % pair_w
    start_x = start_x - pair_w  # 1ペア分左から描き始める

    x = start_x
    while x < WIDTH + pair_w:
        surface.blit(img_a, (x, 0))
        surface.blit(img_b, (x + w, 0))
        x += pair_w


def draw_floor_tiles(surface: pg.Surface, scroll_x: float):
    """
    マリオっぽい床タイルを描画する。
    - GROUND_Y から下をブロックで埋める
    - 横方向はスクロールして流れてるように見せる
    """
    tile = 40  # ブロック1個のサイズ（正方形）

    # スクロール量をタイル単位でループさせる
    start_x = int(scroll_x) % tile  # 0～tile-1
    start_x = start_x - tile        # ちょい左から描く

    # GROUND_Y から下を全部タイルで埋める
    for y in range(GROUND_Y, HEIGHT, tile):
        for x in range(start_x, WIDTH + tile, tile):
            rect = pg.Rect(x, y, tile, tile)
            pg.draw.rect(surface, BLOCK_MAIN, rect, border_radius=4)
            pg.draw.rect(surface, BLOCK_EDGE, rect, width=3, border_radius=4)

            highlight_rect = pg.Rect(x+4, y+4, tile-8, tile-24)
            pg.draw.rect(surface, (220, 180, 80), highlight_rect, border_radius=4)


class Particle(pg.sprite.Sprite):
    """
    障害物破壊時のパーティクルエフェクト
    """
    def __init__(self, x, y, color, size):
        super().__init__()
        self.image = pg.Surface((size, size), pg.SRCALPHA)
        pg.draw.rect(self.image, color, (0, 0, size, size))
        self.rect = self.image.get_rect(center=(x, y))
        self.velocity_x = random.uniform(-5, 5)
        self.velocity_y = random.uniform(-10, -2)
        self.gravity = 0.5
        self.life = 30  # パーティクルの寿命（フレーム数）

    def update(self):
        self.velocity_y += self.gravity
        self.rect.x += self.velocity_x
        self.rect.y += self.velocity_y
        self.life -= 1
        
        # 寿命が尽きたら消滅
        if self.life <= 0:
            self.kill()
            
        # 透明度を徐々に下げる
        alpha = int(255 * (self.life / 30))
        self.image.set_alpha(alpha)


class Car(pg.sprite.Sprite):
    """
    プレイヤー（車）
    ・スペース / ↑ でジャンプ
    ・押しっぱなしでも1回分だけジャンプ
    ・障害物(足場タイプ)の上にも乗れる
    ・ジャンプ時に効果音を鳴らす
    """
    def __init__(self,
                 car_img: pg.Surface,
                 jump_sound: pg.mixer.Sound):
        super().__init__()
        self.image = car_img
        self.rect = self.image.get_rect()
        self.rect.left = 200
        self.rect.bottom = GROUND_Y

        # 物理
        self.vel_y = 0.0
        self.jump_held = False  # 押しっぱなし対策

        # 無敵状態関連
        self.is_invincible = False
        self.invincible_start_time = 0
        self.blink_counter = 0

        # 今フレームの「足場の高さ」
        # 最初は地面
        self.floor_y = GROUND_Y

        # 破壊モード関連
        self.destroy_cooldown = 0  # 破壊クールダウン
        # このフレームでの足場の高さ
        self.floor_y = GROUND_Y

        # 効果音
        self.jump_sound = jump_sound

    def on_ground(self) -> bool:
        return self.rect.bottom >= self.floor_y - 1

    def handle_input(self, key_lst: list[bool]):
        jump_pressed = key_lst[pg.K_SPACE] or key_lst[pg.K_UP]

        # 「新しく押した瞬間」かつ「今は地面/足場の上」
        if jump_pressed and (not self.jump_held) and self.on_ground():
            self.vel_y = JUMP_VELOCITY
            # ジャンプ音を鳴らす
            try:
                self.jump_sound.play()
            except Exception as e:
                print("ジャンプ音エラー:", e)

        # 押しっぱなし管理
        self.jump_held = jump_pressed

        # Shiftキーで障害物破壊（クールダウン中でない場合）
        destroy_flag = False
        if key_lst[pg.K_LSHIFT] and self.destroy_cooldown <= 0:
            destroy_flag = True
            self.destroy_cooldown = 10  # クールダウン設定（10フレーム）
            
        return destroy_flag

    def apply_physics(self):
        # 重力
        self.vel_y += GRAVITY
        # Y移動
        self.rect.y += self.vel_y

        # 足場より下にめりこまない
        if self.rect.bottom >= self.floor_y:
            self.rect.bottom = self.floor_y
            self.vel_y = 0.0

    def activate_invincible(self, current_time: int):
        """
        無敵状態を有効化
        """
        self.is_invincible = True
        self.invincible_start_time = current_time
        self.blink_counter = 0
        
    def update_invincible(self, current_time: int):
        """
        無敵状態の更新
        """
        if self.is_invincible:
            elapsed = current_time - self.invincible_start_time
            if elapsed >= STAR_DURATION_MS:
                self.is_invincible = False
            else:
                self.blink_counter += 1
                
    def update_cooldown(self):
        """
        破壊クールダウンの更新
        """
        if self.destroy_cooldown > 0:
            self.destroy_cooldown -= 1
                
    def should_draw(self) -> bool:
        """
        無敵状態での点滅制御
        """
        if not self.is_invincible:
            return True
        # 点滅効果（5フレームごとに表示/非表示）
        return (self.blink_counter // STAR_BLINK_INTERVAL) % 2 == 0   

    def update(self, key_lst: list[bool]):
        destroy_flag = self.handle_input(key_lst)
        self.apply_physics()
        self.update_cooldown()
        return destroy_flag

    def draw(self, surface: pg.Surface):
        if self.should_draw():  
            surface.blit(self.image, self.rect)


# 足場タイプの横のび倍率
PLATFORM_STRETCH_X = 2.0  # 足場だけ横長にする倍率


class Obstacle(pg.sprite.Sprite):
    """
    障害物
        kind 0 → 踏めば倒せる(スコア +100)
        kind 1 → 踏めば倒せる(スコア +100)
        kind 2 → 踏んだら倒れず足場になる（乗れる / 横に長い足場）
    """
    def __init__(self,
                 base_imgs: list[pg.Surface],
                 world_speed: float,
                 spawn_x: float | None = None):
        super().__init__()

        # 0,1,2 のどれか
        self.kind = random.randint(0, 2)
        src_img = base_imgs[self.kind]

        # ランダムな高さ
        h = random.randint(60, 160)

        # アスペクト比キープで幅
        aspect = src_img.get_width() / src_img.get_height()
        w = int(h * aspect)

        # 足場タイプ(kind 2)だけ横に伸ばす
        if self.kind == 2:
            w = int(w * PLATFORM_STRETCH_X)

        # 安全な範囲にクリップ
        if w < 40:
            w = 40
        if w > 300:
            w = 300

        # スケールして当たり判定用rect作成
        self.image = pg.transform.smoothscale(src_img, (w, h))
        self.rect = self.image.get_rect()

        # 出現位置（画面右の外から）
        if spawn_x is None:
            left_x = WIDTH + random.randint(0, 200)
        else:
            left_x = spawn_x
        self.rect.left = left_x
        self.rect.bottom = GROUND_Y

        self.speed = world_speed
        self.is_destroyed = False
        self.destroy_timer = 0

    def update(self, world_speed: float):
        # 破壊されていない場合のみ移動
        if not self.is_destroyed:
            # 左方向に進める
            self.rect.x -= world_speed

            # 画面外に出たら消す
            if self.rect.right < 0:
                self.kill()
        else:
            # 破壊された場合、タイマーを進める
            self.destroy_timer += 1
            if self.destroy_timer > 15:  # 15フレーム後に完全に消える
                self.kill()
        # 左に動く
        self.rect.x -= world_speed

        # 画面外に出たら消す
        if self.rect.right < 0:
            self.kill()

    def draw(self, surface: pg.Surface):
        if not self.is_destroyed:
            surface.blit(self.image, self.rect)
        else:
            # 破壊された場合、徐々に小さくする
            scale_factor = max(0, 1 - self.destroy_timer / 15)
            if scale_factor > 0:
                scaled_w = int(self.rect.width * scale_factor)
                scaled_h = int(self.rect.height * scale_factor)
                if scaled_w > 0 and scaled_h > 0:
                    scaled_img = pg.transform.scale(self.image, (scaled_w, scaled_h))
                    surface.blit(scaled_img, (self.rect.centerx - scaled_w//2, 
                                             self.rect.centery - scaled_h//2))

    def is_stompable(self) -> bool:
        return self.kind in (0, 1)

    def is_platform(self) -> bool:
        return self.kind == 2
    
    def destroy(self, particles_group: pg.sprite.Group):
        """
        障害物を破壊し、パーティクルエフェクトを生成
        """
        self.is_destroyed = True
        self.destroy_timer = 0
        
        # パーティクルエフェクトを生成
        for _ in range(20):
            x = random.randint(self.rect.left, self.rect.right)
            y = random.randint(self.rect.top, self.rect.bottom)
            size = random.randint(3, 8)
            color = (random.randint(100, 200), random.randint(50, 150), random.randint(0, 50))
            particles_group.add(Particle(x, y, color, size))
    

class StarItem(pg.sprite.Sprite):
    """
    スターアイテム（無敵状態になる）
    """
    def __init__(self, obstacles_group: pg.sprite.Group):
        super().__init__()
        # スター画像を作成（黄色い星）
        self.size = 30
        self.image = pg.Surface((self.size, self.size), pg.SRCALPHA)
        
        # 星形を描画
        points = []
        for i in range(5):
            angle = math.pi/2 + i * 2*math.pi/5
            # 外側の点
            points.append((self.size/2 + self.size/2 * math.cos(angle), 
                          self.size/2 + self.size/2 * math.sin(angle)))
            # 内側の点
            angle += math.pi/5
            points.append((self.size/2 + self.size/4 * math.cos(angle), 
                          self.size/2 + self.size/4 * math.sin(angle)))
        
        pg.draw.polygon(self.image, (255, 255, 0), points)
        
        self.rect = self.image.get_rect()
        
        # 障害物と重ならない位置を探す
        self.find_valid_position(obstacles_group)
        
        self.speed = 8.0  # 固定速度
        
    def find_valid_position(self, obstacles_group: pg.sprite.Group):
        """
        障害物と重ならない位置を探す
        """
        max_attempts = 20  # 最大試行回数
        for _ in range(max_attempts):
            # ランダムなX位置を生成
            x_pos = WIDTH + random.randint(0, 300)
            
            # 高さをランダムに設定（地面より上、画面の上半分）
            y_pos = GROUND_Y - random.randint(50, 200)
            
            # 一時的なrectを作成
            temp_rect = pg.Rect(x_pos, y_pos - self.size, self.size, self.size)
            
            # 障害物との衝突チェック
            collision = False
            for obstacle in obstacles_group:
                if temp_rect.colliderect(obstacle.rect):
                    collision = True
                    break
            
            # 衝突がなければ位置を確定
            if not collision:
                self.rect.bottom = y_pos
                self.rect.left = x_pos
                return
        
        # 最大試行回数に達した場合はデフォルト位置を使用
        self.rect.bottom = GROUND_Y - 100
        self.rect.left = WIDTH + random.randint(0, 300)

    def update(self, world_speed: float):
        # 左方向に進める
        self.rect.x -= world_speed

        # 画面外に出たら消す
        if self.rect.right < 0:
            self.kill()

    def draw(self, surface: pg.Surface):
        surface.blit(self.image, self.rect)


class Score:
    def __init__(self, font: pg.font.Font):
        self.font = font
        self.value = 0
        self.color = TEXT_COLOR
        self.pos = (20, 20)

        # 破壊回数関連
        self.destroy_count = 0  # 現在の破壊回数
        self.last_destroy_threshold = 0  # 最後に破壊回数を増やしたスコア閾値

    def set(self, v: int):
        self.value = v

        # 2000点ごとに破壊回数を増やす
        if self.value >= self.last_destroy_threshold + 2000:
            self.destroy_count += 1
            self.last_destroy_threshold = self.value // 2000 * 2000

    def add(self, delta: int):
        self.value += delta

        # 2000点ごとに破壊回数を増やす
        if self.value >= self.last_destroy_threshold + 2000:
            self.destroy_count += 1
            self.last_destroy_threshold = self.value // 2000 * 2000

    def use_destroy(self):
        """
        破壊回数を使用
        """
        if self.destroy_count > 0:
            self.destroy_count -= 1
            return True
        return False

    def draw(self, screen: pg.Surface):
        img = self.font.render(f"SCORE: {self.value}", True, self.color)
        screen.blit(img, self.pos)

        # 破壊回数表示
        destroy_font = pg.font.SysFont("Meiryo", 20)
        destroy_text = destroy_font.render(f"2000scoreを超えたら、Shiftを押し、前一つの建物を壊す（回数: {self.destroy_count})", True, (255, 0, 0))
        screen.blit(destroy_text, (20, 60))


def get_support_y(car_rect: pg.Rect, obstacles: pg.sprite.Group) -> int:
    """
    いま車が立てる床の高さを返す。
    デフォは地面(GROUND_Y)。
    kind 2 の足場がすぐ下にあればその上を床として返す。
    """
    support_y = GROUND_Y
    for obs in obstacles:
        if not getattr(obs, "is_platform", None):
            continue
        if not obs.is_platform():
            continue

        # x方向で重なってる？
        horizontal_overlap = (
            car_rect.right > obs.rect.left and
            car_rect.left < obs.rect.right
        )

        # 車がその障害物より上側（＝上に乗れる位置）？
        above_top = car_rect.bottom <= obs.rect.top + 5

        if horizontal_overlap and above_top:
            if obs.rect.top < support_y:
                support_y = obs.rect.top

    return support_y


def main():
    pg.init()
    pg.mixer.init()  # サウンド初期化

    # ▼ BGM読み込み&ループ再生 (.wav推奨)
    try:
        pg.mixer.music.load("fig/BGM.wav")
    except Exception as e:
        print("BGMの読み込みでエラー:", e)

    pg.mixer.music.set_volume(0.5)

    try:
        pg.mixer.music.play(-1)  # -1でループ
    except Exception as e:
        print("BGMの再生でエラー:", e)

    # ★ 効果音の読み込み
    try:
        jump_sound = pg.mixer.Sound("fig/janp.wav")
        jump_sound.set_volume(0.6)
    except Exception as e:
        print("ジャンプ音の読み込みでエラー:", e)
        jump_sound = pg.mixer.Sound(buffer=b"\x00\x00")  # 無音ダミー

    try:
        stomp_sound = pg.mixer.Sound("fig/stomp.wav")
        stomp_sound.set_volume(0.7)
    except Exception as e:
        print("踏みつぶし音の読み込みでエラー:", e)
        stomp_sound = pg.mixer.Sound(buffer=b"\x00\x00")  # 無音ダミー

    try:
        gameover_sound = pg.mixer.Sound("fig/gameover.wav")
        gameover_sound.set_volume(0.8)
    except Exception as e:
        print("ゲームオーバー音の読み込みでエラー:", e)
        gameover_sound = pg.mixer.Sound(buffer=b"\x00\x00")  # 無音ダミー

    pg.display.set_caption("CAR RUN (マリオ床ver)")
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    clock = pg.time.Clock()

    # ===== フォント =====
    FONT_NAME = "Meiryo"
    font_big = pg.font.SysFont(FONT_NAME, 64)
    font_small = pg.font.SysFont(FONT_NAME, 32)

    # ===== 背景画像 =====
    bg_img_raw = pg.image.load("fig/hai3.jpg").convert()

    base_h = HEIGHT
    base_w = int(bg_img_raw.get_width() * (base_h / bg_img_raw.get_height()))

    HORIZ_STRETCH = 1.5  # 横にちょっと引きのばしてワイド感
    wide_w = int(base_w * HORIZ_STRETCH)
    wide_h = base_h

    bg_img = pg.transform.smoothscale(bg_img_raw, (wide_w, wide_h))
    bg_img_flip = pg.transform.flip(bg_img, True, False)

    # ===== プレイヤー画像 =====
    raw_car = pg.image.load("fig/3.png").convert_alpha()
    # 左右反転させたい場合は次の1行のコメントアウトを外す
    raw_car = pg.transform.flip(raw_car, True, False)
    car_img = pg.transform.smoothscale(raw_car, (CAR_W, CAR_H))

    # ===== 障害物画像3種 =====
    raw_obst1 = pg.image.load("fig/4.png").convert_alpha()     # stompで消えるタイプ
    raw_obst2 = pg.image.load("fig/5.png").convert_alpha()     # stompで消えるタイプ
    raw_obst3 = pg.image.load("fig/bush2.png").convert_alpha() # 足場タイプ
    

    obstacle_image_list = [raw_obst1, raw_obst2, raw_obst3]

    # ===== ゲーム状態 =====
    car = Car(car_img, jump_sound)
    obstacles = pg.sprite.Group()
    stars = pg.sprite.Group()  # スターアイテムグループ
    particles = pg.sprite.Group()  # パーティクルエフェクトグループ

    world_speed = SPEED_START
    floor_scroll_x = 0.0
    bg_scroll_x = 0.0
    start_ticks = pg.time.get_ticks()
    score_obj = Score(font_small)

    game_active = True
    death_time = None  # ゲームオーバーになった瞬間(ms)

    # 一定間隔で敵を出すイベント
    SPAWN_EVENT = pg.USEREVENT + 1
    pg.time.set_timer(SPAWN_EVENT, SPAWN_INTERVAL_MS)

    # スターアイテムを一定間隔で出すためのイベントタイマー
    STAR_SPAWN_EVENT = pg.USEREVENT + 2
    pg.time.set_timer(STAR_SPAWN_EVENT, STAR_SPAWN_INTERVAL_MS)

    tmr = 0  # フレームカウンタ
    tmr = 0  # デバッグ用カウンタ（今は未使用）

    # =========================
    # メインループ
    # =========================
    while True:
        dt = clock.tick(FPS) / 1000.0
        key_lst = pg.key.get_pressed()
        current_time = pg.time.get_ticks()

        # --- イベント ---
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit()
                sys.exit()

            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    pg.quit()
                    sys.exit()

            if event.type == SPAWN_EVENT and game_active:
                obstacles.add(Obstacle(obstacle_image_list, world_speed))

            # スターアイテムスポーン（ゲーム中のみ）
            if event.type == STAR_SPAWN_EVENT and game_active:
                # 障害物グループを渡して、重ならない位置に生成
                stars.add(StarItem(obstacles))

        # ===== ロジック更新 =====
        # --- ロジック更新 ---
        if game_active:
            elapsed_sec = (pg.time.get_ticks() - start_ticks) / 1000.0

            # スピードだんだん上がる
            world_speed = SPEED_START + SPEED_ACCEL * elapsed_sec

            # 背景と床をスクロール
            bg_scroll_x     -= world_speed
            floor_scroll_x  -= world_speed

            # まず障害物を動かして位置確定
            obstacles.update(world_speed)

            # スターアイテムの更新
            stars.update(world_speed)

            # パーティクルの更新
            particles.update()

            # 次に「いまどこを床にできるか？」を判定してから
            # その床を使って車を動かす
            # 今フレームの床を決めてから車を物理計算
            car.floor_y = get_support_y(car.rect, obstacles)
            destroy_flag = car.update(key_lst)

            # 無敵状態の更新
            car.update_invincible(current_time)

            # 障害物破壊処理
            if destroy_flag and score_obj.destroy_count > 0:
                # 最も近い（最も左にある）障害物を探すが、車の右側にあるものだけ対象
                closest_obstacle = None
                min_x = WIDTH * 2  # 大きな値で初期化
                
                for obs in obstacles:
                    # 破壊されていない、かつ車の右側にある障害物のみ対象
                    if (not obs.is_destroyed and 
                        obs.rect.left > car.rect.right and 
                        obs.rect.right < min_x):
                        min_x = obs.rect.right
                        closest_obstacle = obs
                
                # 最も近い障害物を破壊
                if closest_obstacle:
                    # 破壊回数を消費して障害物を破壊
                    if score_obj.use_destroy():
                        closest_obstacle.destroy(particles)

            # あたり判定
            side_hit = False
            stomped_obstacles = []
            # 無敵状態でない場合のみ障害物との衝突判定を行う
            if not car.is_invincible:
                for obs in obstacles:
                    if not obs.is_destroyed and car.rect.colliderect(obs.rect):

                        # 「上から踏んだ」とみなす条件:
                        landed_from_above = (
                            car.vel_y >= 0 and
                            car.rect.bottom <= obs.rect.top + 20
                        )

                        if landed_from_above:
                            if obs.is_stompable():
                                # 踏める敵 → 倒す & スコア加算 & バウンド
                                stomped_obstacles.append(obs)
                                car.vel_y = BOUNCE_VELOCITY
                                score_obj.add(STOMP_SCORE)

                            elif obs.is_platform():
                                # 足場系 → 上に乗った状態を保証
                                car.floor_y = obs.rect.top
                                car.rect.bottom = obs.rect.top
                                car.vel_y = 0.0

                            else:
                                side_hit = True

            for obs in obstacles:
                if car.rect.colliderect(obs.rect):
                    landed_from_above = (
                        car.vel_y >= 0 and
                        car.rect.bottom <= obs.rect.top + 20
                    )

                    if landed_from_above:
                        if obs.is_stompable():
                            # 踏める敵：消える＋スコア＋バウンド＋効果音
                            stomped_obstacles.append(obs)
                            car.vel_y = BOUNCE_VELOCITY
                            score_obj.add(STOMP_SCORE)
                            try:
                                stomp_sound.play()
                            except Exception as e:
                                print("踏みつぶし音エラー:", e)

                        elif obs.is_platform():
                            # 足場系：上に乗る（ゲームオーバーなし）
                            car.floor_y = obs.rect.top
                            car.rect.bottom = obs.rect.top
                            car.vel_y = 0.0
                        else:
                            # 横や下から当たった → ゲームオーバー
                            side_hit = True
                    else:
                        # 横とか下から当たったらアウト
                        side_hit = True

            # 踏んだ敵をまとめて消す
            for obs in stomped_obstacles:
                obs.kill()

            # ゲームオーバー処理
            if side_hit:
                game_active = False
                death_time = pg.time.get_ticks()

            # 当たり判定：車 vs スターアイテム
            for star in pg.sprite.spritecollide(car, stars, True):
                car.activate_invincible(current_time)

            # ===== スコア更新（時間ベースも反映）=====
                # BGMをフェードアウトさせる
                pg.mixer.music.fadeout(1000)

                # ゲームオーバー音を鳴らす
                try:
                    gameover_sound.play()
                except Exception as e:
                    print("ゲームオーバー音エラー:", e)

            # スコア（時間ベース）もちゃんと反映する
            time_score = int((pg.time.get_ticks() - start_ticks) / 10)
            if score_obj.value < time_score:
                score_obj.set(time_score)

        else:
            # ゲームオーバー後：5秒で終了
            if death_time is not None:
                if pg.time.get_ticks() - death_time >= GAMEOVER_EXIT_DELAY_MS:
                    pg.quit()
                    sys.exit()

        # --- 描画 ---
        draw_bg_scroll(screen, bg_img, bg_img_flip, bg_scroll_x)
        draw_floor_tiles(screen, floor_scroll_x)

        car.draw(screen)

        for obs in obstacles:
            obs.draw(screen)

        # スターアイテム
        for star in stars:
            star.draw(screen)
            
        # パーティクルエフェクト
        particles.draw(screen)

        # スコア
        score_obj.draw(screen)

        # 無敵状態表示
        if car.is_invincible:
            invincible_font = pg.font.SysFont("Meiryo", 24)
            remaining_time = max(0, STAR_DURATION_MS - (current_time - car.invincible_start_time)) / 1000.0
            invincible_text = invincible_font.render(f"無敵時間: {remaining_time:.1f}s", True, (255, 255, 0))
            screen.blit(invincible_text, (WIDTH - 200, 20))

        # ゲームオーバー表示
        score_obj.draw(screen)

        if not game_active:
            draw_text(screen, "GAME OVER", font_big,
                      WIDTH // 2 - 200, HEIGHT // 2 - 120)

            if death_time is not None:
                survival_sec = (death_time - start_ticks) / 1000.0
                draw_text(screen,
                          f"Time: {survival_sec:.2f} s",
                          font_small,
                          WIDTH // 2 - 90,
                          HEIGHT // 2 - 50)

            draw_text(screen,
                      "5秒後に終了します",
                      font_small,
                      WIDTH // 2 - 120,
                      HEIGHT // 2 + 10)

            draw_text(screen,
                      "ESCで今すぐ終了",
                      font_small,
                      WIDTH // 2 - 110,
                      HEIGHT // 2 + 50)

        pg.display.update()
        tmr += 1


if __name__ == "__main__":
    main() 
