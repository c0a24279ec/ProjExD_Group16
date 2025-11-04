import os
import sys
import random
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
BLOCK_MAIN = (180, 120, 40)   # ブロックの茶色い面
BLOCK_EDGE = (110, 70, 20)    # ブロックのふち色（こげ茶）

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

# ゲームオーバー後に自動終了するまでの待ち時間（ミリ秒）
GAMEOVER_EXIT_DELAY_MS = 5000

# 残機の初期値
LIFE_INIT = 3


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
            try:
                self.jump_sound.play()
            except Exception as e:
                print("ジャンプ音エラー:", e)

        # 押しっぱなし管理
        self.jump_held = jump_pressed

    def apply_physics(self):
        # 重力
        self.vel_y += GRAVITY
        # Y移動
        self.rect.y += self.vel_y

        # 足場より下にめりこまない
        if self.rect.bottom >= self.floor_y:
            self.rect.bottom = self.floor_y
            self.vel_y = 0.0

    def update(self, key_lst: list[bool]):
        self.handle_input(key_lst)
        self.apply_physics()

    def draw(self, surface: pg.Surface):
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
        w = max(40, min(w, 300))

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

    def update(self, world_speed: float):
        # 左に動く
        self.rect.x -= world_speed

        # 画面外に出たら消す
        if self.rect.right < 0:
            self.kill()

    def draw(self, surface: pg.Surface):
        surface.blit(self.image, self.rect)

    def is_stompable(self) -> bool:
        return self.kind in (0, 1)

    def is_platform(self) -> bool:
        return self.kind == 2


class Score:
    def __init__(self, font: pg.font.Font):
        self.font = font
        self.value = 0
        self.color = TEXT_COLOR
        self.pos = (20, 20)

    def set(self, v: int):
        self.value = v

    def add(self, delta: int):
        self.value += delta

    def draw(self, screen: pg.Surface):
        img = self.font.render(f"SCORE: {self.value}", True, self.color)
        screen.blit(img, self.pos)


def get_support_y(car_rect: pg.Rect, obstacles: pg.sprite.Group) -> int:
    """
    いま車が立てる床の高さを返す。
    デフォは地面(GROUND_Y)。
    kind 2 の足場がすぐ下にあればその上を床として返す。
    """
    support_y = GROUND_Y
    for obs in obstacles:
        if not hasattr(obs, "is_platform"):
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
            # より高い足場を優先（画面的には上にある方）
            if obs.rect.top < support_y:
                support_y = obs.rect.top

    return support_y


class Life:
    """
    残機表示
    """
    def __init__(self, font: pg.font.Font, init_life: int = LIFE_INIT):
        self.font = font
        self.life = init_life
        self.pos = (20, 60)

    def decrease(self):
        if self.life > 0:
            self.life -= 1

    def increase(self):
        self.life += 1

    def is_dead(self) -> bool:
        return self.life <= 0

    def draw(self, screen: pg.Surface):
        heart = "♥" * self.life if self.life > 0 else ""
        img = self.font.render(f"LIFE: {heart}", True, (200, 30, 30))
        screen.blit(img, self.pos)


class LifeBonus(pg.sprite.Sprite):
    """
    残機を1つ増やすボーナスアイテム（🍄）
    """
    def __init__(self, x, speed):
        super().__init__()
        font = pg.font.SysFont("Meiryo", 48, bold=True)

        # 🍄を透明背景で描画
        self.image = font.render("🍄", True, (0, 200, 0), None).convert_alpha()
        self.rect = self.image.get_rect(midbottom=(x, GROUND_Y))
        self.speed = speed

    def update(self):
        self.rect.x -= self.speed
        if self.rect.right < 0:
            self.kill()


def main():
    pg.init()
    pg.mixer.init()  # サウンド初期化

    # ▼ BGM読み込み&ループ再生 (.wav推奨)
    try:
        pg.mixer.music.load("fig/BGM.wav")
        pg.mixer.music.set_volume(0.5)
        pg.mixer.music.play(-1)  # -1でループ
    except Exception as e:
        print("BGMエラー:", e)

    # 効果音の読み込み
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
        stomp_sound = pg.mixer.Sound(buffer=b"\x00\x00")

    try:
        gameover_sound = pg.mixer.Sound("fig/gameover.wav")
        gameover_sound.set_volume(0.8)
    except Exception as e:
        print("ゲームオーバー音の読み込みでエラー:", e)
        gameover_sound = pg.mixer.Sound(buffer=b"\x00\x00")

    pg.display.set_caption("CAR RUN (マリオ床ver)")
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    clock = pg.time.Clock()

    # ボーナスグループ
    bonus_group = pg.sprite.Group()
    BONUS_EVENT = pg.USEREVENT + 2
    pg.time.set_timer(BONUS_EVENT, 1000)  # 1秒ごとにチェック

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
    # 左右反転（右に走ってるように見せる）
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

    world_speed = SPEED_START
    floor_scroll_x = 0.0
    bg_scroll_x = 0.0
    start_ticks = pg.time.get_ticks()
    score_obj = Score(font_small)
    life_obj = Life(font_small, LIFE_INIT)

    game_active = True
    death_time = None  # ゲームオーバーになった瞬間(ms)

    # 敵出現イベント
    SPAWN_EVENT = pg.USEREVENT + 1
    pg.time.set_timer(SPAWN_EVENT, SPAWN_INTERVAL_MS)

    tmr = 0  # デバッグ用カウンタ

    # =========================
    # メインループ
    # =========================
    while True:
        dt = clock.tick(FPS) / 1000.0
        key_lst = pg.key.get_pressed()

        # --- イベント処理 ---
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit()
                sys.exit()

            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    pg.quit()
                    sys.exit()

            # 敵スポーン
            if event.type == SPAWN_EVENT and game_active:
                obstacles.add(Obstacle(obstacle_image_list, world_speed))

            # 一定確率でライフボーナス（🍄）出現
            if event.type == BONUS_EVENT and game_active:
                if random.random() < 0.2:  # 20%の確率で出現
                    bonus = LifeBonus(WIDTH + random.randint(0, 200),
                                      world_speed)
                    bonus_group.add(bonus)

        # ===== ロジック更新 =====
        if game_active:
            elapsed_sec = (pg.time.get_ticks() - start_ticks) / 1000.0

            # スピードだんだん上がる
            world_speed = SPEED_START + SPEED_ACCEL * elapsed_sec

            # 背景と床をスクロール
            bg_scroll_x -= world_speed
            floor_scroll_x -= world_speed

            # 障害物とボーナスを移動
            obstacles.update(world_speed)
            bonus_group.update()

            # 今フレームの床を決めてから車を物理計算
            car.floor_y = get_support_y(car.rect, obstacles)
            car.update(key_lst)

            # 🍄ボーナス取得判定（ライフ+1）
            if pg.sprite.spritecollide(car, bonus_group, True):
                life_obj.increase()

            # --- 障害物とのあたり判定 ---
            hit_obs = None
            landed_from_above = False
            side_hit = False

            for obs in obstacles:
                if car.rect.colliderect(obs.rect):
                    # 上から踏んだかどうかを判定
                    if car.vel_y >= 0 and car.rect.bottom <= obs.rect.top + 20:
                        landed_from_above = True
                    else:
                        side_hit = True
                    hit_obs = obs
                    break

            if hit_obs:
                if landed_from_above:
                    if hit_obs.is_stompable():
                        # 踏める敵：消える＋スコア＋バウンド＋効果音
                        hit_obs.kill()
                        score_obj.add(STOMP_SCORE)
                        car.vel_y = BOUNCE_VELOCITY
                        try:
                            stomp_sound.play()
                        except Exception as e:
                            print("踏みつぶし音エラー:", e)

                    elif hit_obs.is_platform():
                        # 足場系：上に乗る
                        car.floor_y = hit_obs.rect.top
                        car.rect.bottom = hit_obs.rect.top
                        car.vel_y = 0.0
                    else:
                        side_hit = True
                else:
                    side_hit = True

                # 横などからぶつかった場合：ライフ減少
                if side_hit:
                    hit_obs.kill()
                    life_obj.decrease()
                    if life_obj.is_dead():
                        game_active = False
                        death_time = pg.time.get_ticks()
                        # BGMをフェードアウトさせる
                        pg.mixer.music.fadeout(1000)
                        # ゲームオーバー音を鳴らす
                        try:
                            gameover_sound.play()
                        except Exception as e:
                            print("ゲームオーバー音エラー:", e)

            # スコア（時間ベース）も加算
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

        # ボーナス
        bonus_group.draw(screen)

        # プレイヤー車
        car.draw(screen)

        # 障害物
        for obs in obstacles:
            obs.draw(screen)

        # スコア
        score_obj.draw(screen)

        # 残機
        life_obj.draw(screen)

        # ゲームオーバー表示
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