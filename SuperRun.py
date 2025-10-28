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
GRAVITY = 1.0      # 重力(下向き加速度)
JUMP_VELOCITY = -22   # ジャンプ初速（マイナスで上方向）

# プレイヤーのサイズ
CAR_W = 100
CAR_H = 60

# 障害物スポーン関係
SPAWN_INTERVAL_MS = 1100      # 障害物出現間隔（ミリ秒）
SPEED_START = 8.0             # 最初のスクロール速度
SPEED_ACCEL = 0.05            # 時間がたつと速くなる係数（どんどん速くなる）

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
    """
    左上基準でテキスト描画
    """
    img = font.render(text, True, color)
    surface.blit(img, (x, y))


def check_bound(obj_rct: pg.Rect) -> tuple[bool, bool]:
    """
    画面内判定（元コード由来）
    """
    yoko, tate = True, True
    if obj_rct.left < 0 or WIDTH < obj_rct.right:
        yoko = False
    if obj_rct.top < 0 or HEIGHT < obj_rct.bottom:
        tate = False
    return yoko, tate


def draw_floor_tiles(surface: pg.Surface, scroll_x: float):
    """
    マリオっぽい床タイルを描画する。
    - GROUND_Y から下をブロックで埋める
    - 横方向はスクロールして流れてるように見せる
    """
    tile = 40  # ブロック1個のサイズ（正方形）

    # スクロール量をタイル単位でループさせる
    # 例：-40 から WIDTH+40 くらいまで並べて、隙間が出ないようにする
    start_x = int(scroll_x) % tile  # 0～tile-1
    start_x = start_x - tile        # ちょい左から描く

    # GROUND_Y から下を全部タイルで埋める
    for y in range(GROUND_Y, HEIGHT, tile):
        for x in range(start_x, WIDTH + tile, tile):
            # メインの四角（茶色）
            rect = pg.Rect(x, y, tile, tile)
            pg.draw.rect(surface, BLOCK_MAIN, rect, border_radius=4)

            # ふち（こげ茶）で枠線っぽくしてブロック感を出す
            pg.draw.rect(surface, BLOCK_EDGE, rect, width=3, border_radius=4)

            # ハイライト（上側を少し明るくする）でドット感を出す
            highlight_rect = pg.Rect(x+4, y+4, tile-8, tile-24)
            pg.draw.rect(surface, (220, 180, 80), highlight_rect, border_radius=4)


class Car(pg.sprite.Sprite):
    """
    プレイヤー（車）
    ・スペース / ↑ でジャンプ
    ・押しっぱなしでも1回分だけジャンプ
    """
    def __init__(self, car_img: pg.Surface):
        super().__init__()
        # 車画像
        self.image = car_img
        self.rect = self.image.get_rect()
        # 左寄りに初期配置
        self.rect.left = 200
        self.rect.bottom = GROUND_Y

        # 物理パラメータ
        self.vel_y = 0.0
        self.jump_held = False  # 押しっぱなし対策

    def on_ground(self) -> bool:
        return self.rect.bottom >= GROUND_Y

    def handle_input(self, key_lst: list[bool]):
        """
        ジャンプの入力処理
        「新しく押した瞬間」だけジャンプ。
        押しっぱなしでは連続ジャンプしない。
        """
        jump_pressed = key_lst[pg.K_SPACE] or key_lst[pg.K_UP]

        # 新しく押した瞬間 & 地面にいる → ジャンプ
        if jump_pressed and not self.jump_held and self.on_ground():
            self.vel_y = JUMP_VELOCITY

        # 押しっぱなし状態フラグ更新
        if jump_pressed:
            self.jump_held = True
        else:
            self.jump_held = False

    def apply_physics(self):
        """
        重力と落下処理＋床補正
        """
        # 重力
        self.vel_y += GRAVITY
        # 移動
        self.rect.y += self.vel_y

        # 地面より下に行かない
        if self.rect.bottom >= GROUND_Y:
            self.rect.bottom = GROUND_Y
            self.vel_y = 0.0

    def update(self, key_lst: list[bool]):
        self.handle_input(key_lst)
        self.apply_physics()

    def draw(self, surface: pg.Surface):
        surface.blit(self.image, self.rect)


class Obstacle(pg.sprite.Sprite):
    """
    障害物
    ・右から左へ流れる
    ・ぶつかったらアウト
    """
    def __init__(self, base_img: pg.Surface, world_speed: float):
        super().__init__()

        # ランダムなサイズ（高すぎないように）
        h = random.randint(60, 160)
        w = random.randint(50, 90)

        # 画像をそのサイズにスケール
        self.image = pg.transform.smoothscale(base_img, (w, h))
        self.rect = self.image.get_rect()

        # 画面の少し右の外から出現
        self.rect.left = WIDTH + random.randint(0, 200)
        self.rect.bottom = GROUND_Y

        self.speed = world_speed

    def update(self, world_speed: float):
        # 左方向に進める
        self.rect.x -= world_speed

        # 画面外に出たら消す
        if self.rect.right < 0:
            self.kill()

    def draw(self, surface: pg.Surface):
        surface.blit(self.image, self.rect)


class Score:
    """
    スコア表示
    """
    def __init__(self, font: pg.font.Font):
        self.font = font
        self.value = 0
        self.color = TEXT_COLOR
        self.pos = (20, 20)

    def set(self, v: int):
        self.value = v

    def draw(self, screen: pg.Surface):
        img = self.font.render(f"SCORE: {self.value}", True, self.color)
        screen.blit(img, self.pos)


class Life:
    """
    残機表示
    """
    def __init__(self, font: pg.font.Font, init_life: int = LIFE_INIT):
        self.font = font
        self.life = init_life
        self.pos = (20, 60)

    def decrease(self):
        """
        1減らす
        """
        if self.life > 0:
            self.life -= 1

    def is_dead(self) -> bool:
        """
        残機0かどうか
        """
        return self.life <= 0

    def draw(self, screen: pg.Surface):
        heart = "♥" * self.life if self.life > 0 else ""
        img = self.font.render(f"LIFE: {heart}", True, (200, 30, 30))
        screen.blit(img, self.pos)


class LifeBonus(pg.sprite.Sprite):
    """
    残機を1つ増やすボーナスアイテム
    """
    def __init__(self, x, y, speed):
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
    pg.display.set_caption("CAR RUN (マリオ床ver)")
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    clock = pg.time.Clock()
    bonus_group = pg.sprite.Group()
    BONUS_EVENT = pg.USEREVENT + 2
    pg.time.set_timer(BONUS_EVENT, 1000)  # 1秒ごとにチェック


    # ===== フォントの用意 =====
    # □□になる場合は "Yu Gothic UI" や "MS Gothic" など他の日本語フォント名に変えてOK
    FONT_NAME = "Meiryo"
    font_big = pg.font.SysFont(FONT_NAME, 64)
    font_small = pg.font.SysFont(FONT_NAME, 32)

    # ===== 背景画像のロード =====
    # 元のゲーム背景をそのまま使う
    bg_img_raw = pg.image.load("fig/pg_bg.jpg").convert()
    bg_img = pg.transform.smoothscale(bg_img_raw, (WIDTH, HEIGHT))

    # ===== 車と障害物の画像ロード =====
    # （君のコードでは fig/3.png と fig/4.png を使ってたのでそのまま使う）
    raw_car = pg.image.load("fig/3.png").convert_alpha()
    car_img = pg.transform.smoothscale(raw_car, (CAR_W, CAR_H))

    raw_obst = pg.image.load("fig/4.png").convert_alpha()

    # ===== ゲーム状態の初期化 =====
    car = Car(car_img)
    obstacles = pg.sprite.Group()

    world_speed = SPEED_START            # 現在のスクロール速度
    floor_scroll_x = 0.0                 # 床タイルのスクロール用オフセット
    start_ticks = pg.time.get_ticks()    # 開始時刻(ms)
    score_obj = Score(font_small)
    life_obj = Life(font_small, LIFE_INIT)

    game_active = True
    death_time = None  # ゲームオーバーになった瞬間の時刻(ms)

    # 障害物を一定間隔で出すためのイベントタイマー
    SPAWN_EVENT = pg.USEREVENT + 1
    pg.time.set_timer(SPAWN_EVENT, SPAWN_INTERVAL_MS)

    tmr = 0  # フレームカウンタ（必要なら使える）

    # =========================
    # メインループ
    # =========================
    while True:
        dt = clock.tick(FPS) / 1000.0
        key_lst = pg.key.get_pressed()

        # ===== イベント処理 =====
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit()
                sys.exit()

            if event.type == pg.KEYDOWN:
                # ESCでいつでも強制終了
                if event.key == pg.K_ESCAPE:
                    pg.quit()
                    sys.exit()

            # 障害物スポーン（ゲーム中のみ）
            if event.type == SPAWN_EVENT and game_active:
                obstacles.add(Obstacle(raw_obst, world_speed))

            # 一定確率でボーナス出現
            if event.type == BONUS_EVENT and game_active:
                if random.random() < 0.2:  # 20%の確率で出現
                    bonus = LifeBonus(WIDTH + random.randint(0, 200), GROUND_Y, world_speed)
                    bonus_group.add(bonus)

        # ===== ロジック更新 =====
        if game_active:
            # プレイ経過時間(秒)
            elapsed_sec = (pg.time.get_ticks() - start_ticks) / 1000.0

            # スクロール速度をじわじわ上げる
            world_speed = SPEED_START + SPEED_ACCEL * elapsed_sec

            # 床タイルのスクロール更新（左に流す）
            floor_scroll_x -= world_speed
            # draw_floor_tiles側でmodを取ってるから
            # floor_scroll_x自体は負のままでOK、ループ処理で綺麗につながる

            # 車の更新（ジャンプ/重力）
            car.update(key_lst)

            # 障害物の更新（左に流れる）
            obstacles.update(world_speed)
            
            # ボーナスが流れる
            bonus_group.update()

            # 当たり判定：車 vs 障害物
            for obs in obstacles:
                if car.rect.colliderect(obs.rect):
                    life_obj.decrease()
                    obs.kill() 
                    if life_obj.is_dead():
                        game_active = False
                        death_time = pg.time.get_ticks()
                    break  

            # ボーナス取得判定
            bonus_group.update()
            if pg.sprite.spritecollide(car, bonus_group, True):
                life_obj.life += 1

            # スコア更新（1/100秒単位くらい）
            score_val = int((pg.time.get_ticks() - start_ticks) / 10)
            score_obj.set(score_val)

        else:
            # ゲームオーバー後：5秒経ったら自動終了
            if death_time is not None:
                if pg.time.get_ticks() - death_time >= GAMEOVER_EXIT_DELAY_MS:
                    pg.quit()
                    sys.exit()

        # ===== 描画 =====
        # 背景（元のゲームの背景画像）
        screen.blit(bg_img, (0, 0))

        # マリオっぽい床ブロック
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
