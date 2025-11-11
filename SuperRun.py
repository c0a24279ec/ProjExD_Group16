import os
import sys
import random
import math
import pygame as pg


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
BLOCK_COLORS = [
    (180, 120, 40),  # 1. 元の茶色
    (60, 160, 60),   # 2. 緑色
    (150, 50, 50),   # 3. 赤色
    (100, 100, 150), # 4. 青紫色
]
BLOCK_EDGE_DEFAULT = (110, 70, 20)

# 現在の床色
current_block_main_color = BLOCK_COLORS[0]
current_block_edge_color = BLOCK_EDGE_DEFAULT
current_color_index = 0

# 物理系
GRAVITY = 1.0          # 重力(下向き加速度)
JUMP_VELOCITY = -22    # ジャンプ初速（マイナスで上方向）
BOUNCE_VELOCITY = -12  # 踏みつぶした後の小さいバウンド

# プレイヤーのサイズ
CAR_W = 100
CAR_H = 60

# 障害物スポーン関係
SPAWN_INTERVAL_MS = 1100      # 障害物出現間隔（ミリ秒）
SPEED_START = 8.0             # 最初のスクロール速度
SPEED_ACCEL = 0.05            # 時間がたつと速くなる係数（どんどん速くなる）

# スコア系
STOMP_SCORE = 100             # 踏みつぶし時に入るスコア
GOAL_SCORE = 300           # ゴールスコア

# ゲームオーバー/クリア後に自動終了するまでの待ち時間（ミリ秒）
GAMEOVER_EXIT_DELAY_MS = 5000

# 残機の初期値
LIFE_INIT = 3

# ランダムイベントのリスト
EVENT_LST = ["speed_up", "speed_down"]

# アイテム関係
STAR_DURATION_MS = 4000       # スター効果持続時間（ミリ秒）
STAR_SPAWN_INTERVAL_MS = 8000 # スター出現間隔（ミリ秒）
STAR_BLINK_INTERVAL = 5       # 点滅間隔（フレーム）

# 足場タイプの横のび倍率
PLATFORM_STRETCH_X = 2.0      # 足場だけ横長にする倍率


# =========================
# 共通描画関数
# =========================
def draw_text(surface, text, font, x, y, color=TEXT_COLOR):
    """左上基準でテキスト描画"""
    img = font.render(text, True, color)
    surface.blit(img, (x, y))


def draw_bg_scroll(surface, img_a, img_b, scroll_x):
    """
    背景を横スクロールでループ表示する。
    img_a と img_b(左右反転) を A|B|A|B|... でつなぐ。
    """
    w = img_a.get_width()
    pair_w = w * 2  # [A|B] セットの幅

    start_x = int(scroll_x) % pair_w
    start_x -= pair_w  # 1ペア分左から描き始める

    x = start_x
    while x < WIDTH + pair_w:
        surface.blit(img_a, (x, 0))
        surface.blit(img_b, (x + w, 0))
        x += pair_w


def draw_floor_tiles(surface, scroll_x):
    """
    マリオっぽい床タイルを描画する。
    - GROUND_Y から下をブロックで埋める
    - 横方向はスクロールして流れてるように見せる
    """
    global current_block_main_color, current_block_edge_color

    tile = 40  # ブロック1個のサイズ（正方形）

    # スクロール量をタイル単位でループさせる
    start_x = int(scroll_x) % tile
    start_x -= tile

    # GROUND_Y から下を全部タイルで埋める（現在の色で描画）
    for y in range(GROUND_Y, HEIGHT, tile):
        for x in range(start_x, WIDTH + tile, tile):
            rect = pg.Rect(x, y, tile, tile)
            pg.draw.rect(surface, current_block_main_color, rect, border_radius=4)
            pg.draw.rect(surface, current_block_edge_color, rect, width=3, border_radius=4)

            highlight_rect = pg.Rect(x + 4, y + 4, tile - 8, tile - 24)
            pg.draw.rect(surface, (220, 180, 80), highlight_rect, border_radius=4)


# =========================
# パーティクル
# =========================
class Particle(pg.sprite.Sprite):
    """障害物破壊時のパーティクルエフェクト"""
    def __init__(self, x, y, color, size):
        super().__init__()
        self.image = pg.Surface((size, size), pg.SRCALPHA)
        pg.draw.rect(self.image, color, (0, 0, size, size))
        self.rect = self.image.get_rect(center=(x, y))
        self.vx = random.uniform(-5, 5)
        self.vy = random.uniform(-10, -2)
        self.g = 0.5
        self.life = 30  # 寿命（フレーム）

    def update(self):
        self.vy += self.g
        self.rect.x += self.vx
        self.rect.y += self.vy
        self.life -= 1

        if self.life <= 0:
            self.kill()
            return

        alpha = int(255 * (self.life / 30))
        self.image.set_alpha(alpha)


# =========================
# プレイヤー（車）
# =========================
class Car(pg.sprite.Sprite):
    """
    プレイヤー（車）
    ・SPACE / ↑ でジャンプ（押しっぱなしは1回だけ）
    ・足場タイプの障害物の上に乗れる
    ・ジャンプ時に効果音
    ・Shiftで前方の障害物を破壊（スコア条件つき）
    ・スター取得中は無敵で点滅
    """
    def __init__(self, car_img, jump_sound=None):
        super().__init__()
        self.image = car_img
        self.rect = self.image.get_rect()
        self.rect.left = 200
        self.rect.bottom = GROUND_Y

        # 物理
        self.vel_y = 0.0
        self.jump_held = False  # 押しっぱなし判定用

        # 無敵
        self.is_invincible = False
        self.invincible_start_time = 0
        self.blink_counter = 0

        # 足場の高さ
        self.floor_y = GROUND_Y

        # Shift破壊クールダウン
        self.destroy_cooldown = 0

        self.jump_sound = jump_sound

    def on_ground(self):
        return self.rect.bottom >= self.floor_y - 1

    def handle_input(self, key_lst):
        jump_pressed = key_lst[pg.K_SPACE] or key_lst[pg.K_UP]

        # 新しく押した瞬間 & 足場の上 → ジャンプ
        if jump_pressed and (not self.jump_held) and self.on_ground():
            self.vel_y = JUMP_VELOCITY
            if self.jump_sound is not None:
                try:
                    self.jump_sound.play()
                except Exception as e:
                    print("ジャンプ音エラー:", e)

        self.jump_held = jump_pressed

        # Shift → 障害物破壊要求フラグ
        destroy_flag = False
        if key_lst[pg.K_LSHIFT] and self.destroy_cooldown <= 0:
            destroy_flag = True
            self.destroy_cooldown = 10  # 10フレームクールダウン

        return destroy_flag

    def apply_physics(self):
        self.vel_y += GRAVITY
        self.rect.y += self.vel_y

        # 足場より下に行かない
        if self.rect.bottom >= self.floor_y:
            self.rect.bottom = self.floor_y
            self.vel_y = 0.0

    def activate_invincible(self, current_time):
        self.is_invincible = True
        self.invincible_start_time = current_time
        self.blink_counter = 0

    def update_invincible(self, current_time):
        if self.is_invincible:
            elapsed = current_time - self.invincible_start_time
            if elapsed >= STAR_DURATION_MS:
                self.is_invincible = False
            else:
                self.blink_counter += 1

    def update_cooldown(self):
        if self.destroy_cooldown > 0:
            self.destroy_cooldown -= 1

    def should_draw(self):
        if not self.is_invincible:
            return True
        # 無敵中は点滅
        return (self.blink_counter // STAR_BLINK_INTERVAL) % 2 == 0

    def update(self, key_lst):
        destroy_flag = self.handle_input(key_lst)
        self.apply_physics()
        self.update_cooldown()
        return destroy_flag

    def draw(self, surface):
        if self.should_draw():
            surface.blit(self.image, self.rect)

# =========================
# ゴール旗クラス（画像）
# =========================
class Goal(pg.sprite.Sprite):
    """旗画像のゴール。プレイヤーが触れるとクリア。"""
    def __init__(self, x, y):
        super().__init__()
        # 旗画像を読み込み
        img = pg.image.load("fig/goal.jpg").convert_alpha()

        # 好きな大きさに調整（高さ120pxに合わせる例）
        FLAG_H = 120
        aspect = img.get_width() / img.get_height()
        FLAG_W = int(FLAG_H * aspect)
        self.image = pg.transform.smoothscale(img, (FLAG_W, FLAG_H))

        self.rect = self.image.get_rect(midbottom=(x, y))

    def update(self, world_speed):
        # 画面に合わせて左に流れる
        self.rect.x -= world_speed
        if self.rect.right < 0:
            self.kill()


# =========================
# 障害物
# =========================
class Obstacle(pg.sprite.Sprite):
    """
    障害物 
        kind 0 → 踏めば倒せる(スコア +100)
        kind 1 → 踏めば倒せる(スコア +100)
        kind 2 → 足場になる（乗れる / 横に長い足場）
    """
    def __init__(self, base_imgs, world_speed, spawn_x=None):
        super().__init__()

        self.kind = random.randint(0, 2)
        src_img = base_imgs[self.kind]

        # ランダムな高さ
        h = random.randint(60, 160)
        aspect = src_img.get_width() / src_img.get_height()
        w = int(h * aspect)

        if self.kind == 2:
            w = int(w * PLATFORM_STRETCH_X)

        w = max(40, min(w, 300))

        self.original_image = pg.transform.smoothscale(src_img, (w, h))
        self.image = self.original_image.copy()
        self.rect = self.image.get_rect()

        if spawn_x is None:
            left_x = WIDTH + random.randint(0, 200)
        else:
            left_x = spawn_x
        self.rect.left = left_x
        self.rect.bottom = GROUND_Y

        self.speed = world_speed
        self.is_destroyed = False
        self.destroy_timer = 0

    def update(self, world_speed):
        if not self.is_destroyed:
            self.rect.x -= world_speed
            if self.rect.right < 0:
                self.kill()
        else:
            # 破壊アニメ（少し小さくして消える）
            self.destroy_timer += 1
            if self.destroy_timer > 15:
                self.kill()

    def draw(self, surface):
        if not self.is_destroyed:
            surface.blit(self.image, self.rect)
        else:
            scale_factor = max(0, 1 - self.destroy_timer / 15)
            if scale_factor <= 0:
                return
            scaled_w = int(self.rect.width * scale_factor)
            scaled_h = int(self.rect.height * scale_factor)
            if scaled_w <= 0 or scaled_h <= 0:
                return
            scaled_img = pg.transform.scale(self.original_image, (scaled_w, scaled_h))
            surface.blit(
                scaled_img,
                (self.rect.centerx - scaled_w // 2,
                 self.rect.centery - scaled_h // 2),
            )

    def is_stompable(self):
        return self.kind in (0, 1)

    def is_platform(self):
        return self.kind == 2

    def destroy(self, particles_group):
        """障害物を破壊し、パーティクルを生成"""
        if self.is_destroyed:
            return
        self.is_destroyed = True
        self.destroy_timer = 0

        for _ in range(20):
            x = random.randint(self.rect.left, self.rect.right)
            y = random.randint(self.rect.top, self.rect.bottom)
            size = random.randint(3, 8)
            color = (
                random.randint(100, 200),
                random.randint(50, 150),
                random.randint(0, 50),
            )
            particles_group.add(Particle(x, y, color, size))


# =========================
# スターアイテム
# =========================
class StarItem(pg.sprite.Sprite):
    """スターアイテム（取ると無敵）"""
    def __init__(self, obstacles_group):
        super().__init__()
        self.size = 30
        self.image = pg.Surface((self.size, self.size), pg.SRCALPHA)

        # 星形
        points = []
        for i in range(5):
            angle = math.pi / 2 + i * 2 * math.pi / 5
            points.append((
                self.size / 2 + self.size / 2 * math.cos(angle),
                self.size / 2 + self.size / 2 * math.sin(angle)
            ))
            angle += math.pi / 5
            points.append((
                self.size / 2 + self.size / 4 * math.cos(angle),
                self.size / 2 + self.size / 4 * math.sin(angle)
            ))
        pg.draw.polygon(self.image, (255, 255, 0), points)

        self.rect = self.image.get_rect()
        self._find_valid_position(obstacles_group)
        self.speed = 8.0

    def _find_valid_position(self, obstacles_group):
        max_attempts = 20
        for _ in range(max_attempts):
            x_pos = WIDTH + random.randint(0, 300)
            y_pos = GROUND_Y - random.randint(50, 200)
            temp_rect = pg.Rect(x_pos, y_pos - self.size, self.size, self.size)

            if any(temp_rect.colliderect(ob.rect) for ob in obstacles_group):
                continue

            self.rect.left = x_pos
            self.rect.bottom = y_pos
            return

        # 見つからなかったときの保険位置
        self.rect.left = WIDTH + random.randint(0, 300)
        self.rect.bottom = GROUND_Y - 100

    def update(self, world_speed):
        self.rect.x -= world_speed
        if self.rect.right < 0:
            self.kill()

    def draw(self, surface):
        surface.blit(self.image, self.rect)


# =========================
# スコア＆仲間カー
# =========================
class Score:
    """スコアと仲間カー、Shift破壊ストックを管理"""
    def __init__(self, font, car, car_img):
        self.font = font
        self.value = 0
        self.multiplier = 1.0
        self.color = TEXT_COLOR
        self.pos = (20, 20)

        self.car = car
        self.car_img = car_img
        self.friends = []

        # Shift破壊関連
        self.destroy_count = 0
        self.last_destroy_threshold = 0

        self.destroy_font = pg.font.SysFont("Meiryo", 20)

    def _update_destroy_count(self):
        # 2000点ごとに破壊ストック +1
        while self.value >= self.last_destroy_threshold + 2000:
            self.destroy_count += 1
            self.last_destroy_threshold += 2000

    def set(self, v):
        self.value = v
        self._update_destroy_count()

    def add(self, points):
        self.value += int(points * self.multiplier)
        self._update_destroy_count()

    def bonus(self, kind):
        if kind == "obstacle_break":
            self.add(100)
        elif kind == "life_up":
            self.add(200)

    def use_destroy(self):
        """Shift破壊ストックを1つ消費"""
        if self.destroy_count > 0:
            self.destroy_count -= 1
            return True
        return False

    def update_friends(self, key_lst):
        for friend in self.friends:
            friend.update(key_lst)

    def draw_friends(self, screen):
        for friend in self.friends:
            friend.draw(screen)

    def check_for_friends(self):
        """スコアに応じて仲間カーを追加"""
        if self.value >= 2000 and len(self.friends) == 0:
            new_friend = FriendCar(self.car_img,
                                   self.car.rect.left - 100,
                                   GROUND_Y,
                                   self.car)
            self.friends.append(new_friend)
        if self.value >= 5000 and len(self.friends) == 1:
            new_friend2 = FriendCar(self.car_img,
                                    self.car.rect.left - 200,
                                    GROUND_Y,
                                    self.car)
            self.friends.append(new_friend2)

    def draw(self, screen):
        img = self.font.render(f"SCORE: {self.value}", True, self.color)
        screen.blit(img, self.pos)

        txt = f"2000scoreを超えたら、Shiftで前の建物を破壊（回数: {self.destroy_count}）"
        dimg = self.destroy_font.render(txt, True, (255, 0, 0))
        screen.blit(dimg, (20, 60))


class FriendCar(Car):
    """仲間カー（プレイヤーの後ろを追従）"""
    def __init__(self, car_img, spawn_x, spawn_y, target_car):
        super().__init__(car_img, jump_sound=None)
        self.rect.left = spawn_x
        self.rect.bottom = spawn_y
        self.target_car = target_car

        self.follow_distance = 100
        self.ease = 0.12

    def update(self, key_lst):
        # 親の update でジャンプ/重力処理
        super().update(key_lst)

        # X方向：プレイヤーの少し後ろに追従
        target_x = self.target_car.rect.left - self.follow_distance
        dx = target_x - self.rect.left
        if abs(dx) > 1:
            self.rect.left += int(dx * self.ease)

        # Y方向：プレイヤーに近づける
        dy = self.target_car.rect.bottom - self.rect.bottom
        if abs(dy) > 1:
            self.rect.bottom += int(dy * self.ease)

    def draw(self, screen):
        if self.should_draw():
            screen.blit(self.image, self.rect)


# =========================
# サポート関数
# =========================
def get_support_y(car_rect, obstacles):
    """
    車が今フレーム「どこを床として扱えるか」を計算して返す。
       デフォルトは地面(GROUND_Y)。
       kind 2（足場タイプ）の障害物が真下にあれば、その天面を床にする。
    """
    support_y = GROUND_Y
    for obs in obstacles:
        if getattr(obs, "is_destroyed", False):
            continue
        if not hasattr(obs, "is_platform") or not obs.is_platform():
            continue

        horizontal_overlap = (
            car_rect.right > obs.rect.left and
            car_rect.left < obs.rect.right
        )
        above_top = car_rect.bottom <= obs.rect.top + 5

        if horizontal_overlap and above_top:
            if obs.rect.top < support_y:
                support_y = obs.rect.top

    return support_y


class Event:
    """ランダム速度イベント"""
    def __init__(self, font: pg.font.Font):
        self.addspeed = 1.0
        self.active = False
        self.start_time = 0
        self.end_time = 0
        self.font = font
        self.value = ""
        self.color = TEXT_COLOR
        self.pos = (WIDTH // 2 - 80, 20)

    def set(self, event_name: str):
        self.value = event_name

    def draw(self, screen: pg.Surface):
        img = self.font.render(f"EVENT: {self.value}", True, self.color)
        screen.blit(img, self.pos)

    def select(self, event_lst: list):
        e = event_lst[random.randint(0, len(event_lst) - 1)]
        return e

    def start(self, event_name: str):
        if event_name == "speed_up":
            self.addspeed = 1.5
            self.end_time = 10000
        elif event_name == "speed_down":
            self.addspeed = 0.8
            self.end_time = 10000
        else:
            self.addspeed = 1.0
            self.end_time = 0

        self.start_time = pg.time.get_ticks()
        self.active = True

    def update(self):
        # 一定時間経過したらリセット
        if self.active and pg.time.get_ticks() - self.start_time > self.end_time:
            self.addspeed = 1.0
            self.value = ""
            self.active = False


# =========================
# ライフ＆ボーナス
# =========================
class Life:
    """残機表示"""
    def __init__(self, font, init_life=LIFE_INIT):
        self.font = font
        self.life = init_life
        self.pos = (20, 90)

    def decrease(self):
        if self.life > 0:
            self.life -= 1

    def increase(self):
        self.life += 1

    def is_dead(self):
        return self.life <= 0

    def draw(self, screen):
        heart = "♥" * self.life if self.life > 0 else ""
        img = self.font.render(f"LIFE: {heart}", True, (200, 30, 30))
        screen.blit(img, self.pos)


class LifeBonus(pg.sprite.Sprite):
    """残機+1ボーナス（🍄）"""
    def __init__(self, x, speed):
        super().__init__()
        font = pg.font.SysFont("Meiryo", 48, bold=True)
        self.image = font.render("🍄", True, (0, 200, 0), None).convert_alpha()
        self.rect = self.image.get_rect(midbottom=(x, GROUND_Y))
        self.speed = speed

    def update(self):
        self.rect.x -= self.speed
        if self.rect.right < 0:
            self.kill()


# =========================
# メイン
# =========================
def main():
    pg.init()
    pg.mixer.init()

    # BGM
    try:
        pg.mixer.music.load("fig/BGM.wav")
        pg.mixer.music.set_volume(0.5)
        pg.mixer.music.play(-1)
    except Exception as e:
        print("BGMエラー:", e)

    # 効果音
    try:
        jump_sound = pg.mixer.Sound("fig/janp.wav")
        jump_sound.set_volume(0.6)
    except Exception as e:
        print("ジャンプ音読み込みエラー:", e)
        jump_sound = None

    try:
        stomp_sound = pg.mixer.Sound("fig/stomp.wav")
        stomp_sound.set_volume(0.7)
    except Exception as e:
        print("踏みつぶし音読み込みエラー:", e)
        stomp_sound = None

    try:
        gameover_sound = pg.mixer.Sound("fig/gameover.wav")
        gameover_sound.set_volume(0.8)
    except Exception as e:
        print("ゲームオーバー音読み込みエラー:", e)
        gameover_sound = None

    pg.display.set_caption("CAR RUN (マリオ床ver)")
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    clock = pg.time.Clock()

    # フォント
    FONT_NAME = "Meiryo"
    font_big = pg.font.SysFont(FONT_NAME, 64)
    font_small = pg.font.SysFont(FONT_NAME, 32)

    # 背景
    bg_img_raw = pg.image.load("fig/hai3.jpg").convert()
    base_h = HEIGHT
    base_w = int(bg_img_raw.get_width() * (base_h / bg_img_raw.get_height()))
    HORIZ_STRETCH = 1.5
    wide_w = int(base_w * HORIZ_STRETCH)
    wide_h = base_h
    bg_img = pg.transform.smoothscale(bg_img_raw, (wide_w, wide_h))
    bg_img_flip = pg.transform.flip(bg_img, True, False)

    # 車
    raw_car = pg.image.load("fig/3.png").convert_alpha()
    raw_car = pg.transform.flip(raw_car, True, False)  # 右向き
    car_img = pg.transform.smoothscale(raw_car, (CAR_W, CAR_H))

    # 障害物画像
    raw_obst1 = pg.image.load("fig/4.png").convert_alpha()
    raw_obst2 = pg.image.load("fig/5.png").convert_alpha()
    raw_obst3 = pg.image.load("fig/bush2.png").convert_alpha()
    obstacle_image_list = [raw_obst1, raw_obst2, raw_obst3]

    # ゲームオブジェクト
    car = Car(car_img, jump_sound)
    obstacles = pg.sprite.Group()
    bonus_group = pg.sprite.Group()
    stars = pg.sprite.Group()
    particles = pg.sprite.Group()
    goal_group = pg.sprite.Group()
    goal = None


    world_speed = SPEED_START
    floor_scroll_x = 0.0
    bg_scroll_x = 0.0
    start_ticks = pg.time.get_ticks()

    score_obj = Score(font_small, car, car_img)
    life_obj = Life(font_small, LIFE_INIT)
    random_event = Event(font_small)

    game_active = True
    game_clear = False
    end_time = None

    # イベントID
    SPAWN_EVENT = pg.USEREVENT + 1
    BONUS_EVENT = pg.USEREVENT + 2
    STAR_SPAWN_EVENT = pg.USEREVENT + 3
    RANDOM_EVENT = pg.USEREVENT + 4  # ランダムイベント

    # タイマー設定
    pg.time.set_timer(SPAWN_EVENT, SPAWN_INTERVAL_MS)
    pg.time.set_timer(BONUS_EVENT, 1000)  # 1秒ごとに🍄チャンス
    pg.time.set_timer(STAR_SPAWN_EVENT, STAR_SPAWN_INTERVAL_MS)
    pg.time.set_timer(RANDOM_EVENT, 40000)  # 40秒ごとにランダムイベント

    tmr = 0  # デバッグ用カウンタ（今は未使用）

    global current_color_index, current_block_main_color, current_block_edge_color

    # =========================
    # ループ
    # =========================
    while True:
        dt = clock.tick(FPS) / 1000.0
        key_lst = pg.key.get_pressed()
        current_time = pg.time.get_ticks()

        # ---- イベント処理 ----
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit()
                sys.exit()

            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    pg.quit()
                    sys.exit()

                # 床の色変更：Mキー
                if event.key == pg.K_m and game_active:
                    current_color_index = (current_color_index + 1) % len(BLOCK_COLORS)
                    current_block_main_color = BLOCK_COLORS[current_color_index]
                    current_block_edge_color = BLOCK_EDGE_DEFAULT

            if not game_active:
                continue

            if event.type == SPAWN_EVENT:
                obstacles.add(Obstacle(obstacle_image_list, world_speed))

            if event.type == BONUS_EVENT:
                if random.random() < 0.2:
                    bonus = LifeBonus(WIDTH + random.randint(0, 200), world_speed)
                    bonus_group.add(bonus)

            if event.type == STAR_SPAWN_EVENT:
                stars.add(StarItem(obstacles))

            if event.type == RANDOM_EVENT:
                event_name = random_event.select(EVENT_LST)
                random_event.set(event_name)
                random_event.start(event_name)

        # --- ロジック更新 ---
        if game_active:
            # ランダムイベントの効果更新
            random_event.update()

            elapsed_sec = (current_time - start_ticks) / 1000.0

            # スピードだんだん上がる + イベント補正
            world_speed = (SPEED_START + SPEED_ACCEL * elapsed_sec) * random_event.addspeed

            bg_scroll_x -= world_speed
            floor_scroll_x -= world_speed

            obstacles.update(world_speed)
            bonus_group.update()
            stars.update(world_speed)
            particles.update()

            # 足場を計算してから車を更新
            car.floor_y = get_support_y(car.rect, obstacles)
            destroy_flag = car.update(key_lst)
            car.update_invincible(current_time)

            # スター取得
            if pg.sprite.spritecollide(car, stars, True):
                car.activate_invincible(current_time)

            # きのこ取得 → ライフ+1
            if pg.sprite.spritecollide(car, bonus_group, True):
                life_obj.increase()
                score_obj.bonus("life_up")

            # Shiftで前方の一番近い障害物を破壊
            if destroy_flag and score_obj.destroy_count > 0:
                closest_obstacle = None
                min_x = WIDTH * 2
                for obs in obstacles:
                    if obs.is_destroyed:
                        continue
                    if obs.rect.left > car.rect.right and obs.rect.right < min_x:
                        min_x = obs.rect.right
                        closest_obstacle = obs
                if closest_obstacle and score_obj.use_destroy():
                    closest_obstacle.destroy(particles)
                    score_obj.bonus("obstacle_break")

            # 障害物との当たり判定
            side_hit = False

            for obs in obstacles:
                if obs.is_destroyed:
                    continue
                if not car.rect.colliderect(obs.rect):
                    continue

                landed_from_above = (
                    car.vel_y >= 0 and
                    car.rect.bottom <= obs.rect.top + 20
                )

                if landed_from_above:
                    if obs.is_stompable():
                        obs.destroy(particles)
                        score_obj.add(STOMP_SCORE)
                        car.vel_y = BOUNCE_VELOCITY
                        if stomp_sound is not None:
                            try:
                                stomp_sound.play()
                            except Exception as e:
                                print("踏みつぶし音エラー:", e)
                    elif obs.is_platform():
                        car.floor_y = obs.rect.top
                        car.rect.bottom = obs.rect.top
                        car.vel_y = 0.0
                    else:
                        if not car.is_invincible:
                            side_hit = True
                else:
                    # 横・下から衝突
                    if not car.is_invincible:
                        side_hit = True
                    else:
                        # 無敵中はぶつかると破壊
                        obs.destroy(particles)

                if side_hit and not car.is_invincible:
                    obs.destroy(particles)
                    life_obj.decrease()
                    if life_obj.is_dead():
                        game_active = False
                        game_clear = False
                        end_time = current_time
                        pg.mixer.music.fadeout(1000)
                        if gameover_sound is not None:
                            try:
                                gameover_sound.play()
                            except Exception as e:
                                print("ゲームオーバー音エラー:", e)
                    break

            # 時間ベーススコア
            time_score = int((current_time - start_ticks) / 10)
            if score_obj.value < time_score:
                score_obj.set(time_score)

            # 仲間カーの管理
            score_obj.check_for_friends()
            score_obj.update_friends(key_lst)

            # ★ ゴール旗の出現＆判定 ★
            # スコアがGOAL_SCOREになったら、右側に旗を出す
            if goal is None and score_obj.value >= GOAL_SCORE:
                goal = Goal(WIDTH + 150, GROUND_Y)
                goal_group.add(goal)

            # ゴール旗の移動
            goal_group.update(world_speed)

            # プレイヤーのX座標が、旗のX座標を超えたらクリア扱い
            if goal and car.rect.centerx >= goal.rect.centerx:
                game_active = False
                game_clear = True
                end_time = current_time
                pg.mixer.music.fadeout(1000)

           

        else:
            # ゲームオーバー/クリア後 5秒で終了
            if end_time is not None and current_time - end_time >= GAMEOVER_EXIT_DELAY_MS:
                pg.quit()
                sys.exit()

        # ---- 描画 ----
        draw_bg_scroll(screen, bg_img, bg_img_flip, bg_scroll_x)
        draw_floor_tiles(screen, floor_scroll_x)

        bonus_group.draw(screen)
        for star in stars:
            star.draw(screen)
        particles.draw(screen)

        # プレイヤー＆仲間
        car.draw(screen)
        score_obj.draw_friends(screen)

        # 障害物
        for obs in obstacles:
            obs.draw(screen)
        
        # ゴール旗
        goal_group.draw(screen)


        # スコア＆ライフ
        score_obj.draw(screen)
        life_obj.draw(screen)

        # 無敵残り時間表示
        if car.is_invincible:
            invincible_font = pg.font.SysFont("Meiryo", 24)
            remaining_time = max(
                0,
                STAR_DURATION_MS - (current_time - car.invincible_start_time)
            ) / 1000.0
            inv_text = invincible_font.render(
                f"無敵時間: {remaining_time:.1f}s", True, (255, 255, 0)
            )
            screen.blit(inv_text, (WIDTH - 220, 20))

        # イベント名表示
        random_event.draw(screen)

        # ゲームオーバー / ゴール表示
        if not game_active:
            if game_clear:
                # ゴールしたとき
                draw_text(screen, "GOAL!!", font_big,
                          WIDTH // 2 - 130, HEIGHT // 2 - 120)
                if end_time is not None:
                    survival_sec = (end_time - start_ticks) / 1000.0
                    draw_text(screen,
                              f"Time: {survival_sec:.2f} s",
                              font_small,
                              WIDTH // 2 - 90,
                              HEIGHT // 2 - 50)
                draw_text(screen,
                          "クリア！おつかれさま！",
                          font_small,
                          WIDTH // 2 - 130,
                          HEIGHT // 2 + 10)
                draw_text(screen,
                          "5秒後に終了します / ESCで即終了",
                          font_small,
                          WIDTH // 2 - 200,
                          HEIGHT // 2 + 50)
            else:
                # ゲームオーバー
                draw_text(screen, "GAME OVER", font_big,
                          WIDTH // 2 - 200, HEIGHT // 2 - 120)

                if end_time is not None:
                    survival_sec = (end_time - start_ticks) / 1000.0
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

