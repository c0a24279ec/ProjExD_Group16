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
            # メインの四角（茶色）
            rect = pg.Rect(x, y, tile, tile)
            pg.draw.rect(surface, BLOCK_MAIN, rect, border_radius=4)

            # ふち（こげ茶）で枠線っぽくしてブロック感を出す
            pg.draw.rect(surface, BLOCK_EDGE, rect, width=3, border_radius=4)

            # ハイライト（上側を少し明るくする）
            highlight_rect = pg.Rect(x+4, y+4, tile-8, tile-24)
            pg.draw.rect(surface, (220, 180, 80), highlight_rect, border_radius=4)


class Car(pg.sprite.Sprite):
    """
    プレイヤー（車）
    ・スペース / ↑ でジャンプ
    ・押しっぱなしでも1回分だけジャンプ
    ・障害物(足場タイプ)の上にも乗れる
    """
    def __init__(self, car_img: pg.Surface):
        super().__init__()
        self.image = car_img
        self.rect = self.image.get_rect()
        self.rect.left = 200
        self.rect.bottom = GROUND_Y

        # 物理パラメータ
        self.vel_y = 0.0
        self.jump_held = False  # 押しっぱなし対策

        # 今フレームの「足場の高さ」
        # 最初は地面
        self.floor_y = GROUND_Y

    def on_ground(self) -> bool:
        # 今決まっている floor_y の上に立ってるなら「地面にいる」とみなす
        return self.rect.bottom >= self.floor_y - 1

    def handle_input(self, key_lst: list[bool]):
        """
        ジャンプの入力処理
        「新しく押した瞬間」だけジャンプ。
        押しっぱなしでは連続ジャンプしない。
        """
        jump_pressed = key_lst[pg.K_SPACE] or key_lst[pg.K_UP]

        # 新しく押した瞬間 & 足場の上 → ジャンプ
        if jump_pressed and (not self.jump_held) and self.on_ground():
            self.vel_y = JUMP_VELOCITY

        # 押しっぱなし状態フラグ更新
        if jump_pressed:
            self.jump_held = True
        else:
            self.jump_held = False

    def apply_physics(self):
        """
        重力と落下処理＋足場補正
        floor_y を基準にして下に落ちすぎないようにする
        """
        # 重力
        self.vel_y += GRAVITY
        # 移動
        self.rect.y += self.vel_y

        # 足場より下に行かない
        if self.rect.bottom >= self.floor_y:
            self.rect.bottom = self.floor_y
            self.vel_y = 0.0

    def update(self, key_lst: list[bool]):
        self.handle_input(key_lst)
        self.apply_physics()

    def draw(self, surface: pg.Surface):
        surface.blit(self.image, self.rect)


# ★ 追加：足場タイプの横のび倍率
PLATFORM_STRETCH_X = 2.0  # 2.0なら横2倍。好きな幅に調整してOK


class Obstacle(pg.sprite.Sprite):
    """
    障害物 
    ・右から左へ流れる
    ・3種類のタイプを持つ
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

        # ランダムな高さ（高すぎないように制限）
        h = random.randint(60, 160)

        # 幅は元画像のアスペクト比を使って決める
        aspect = src_img.get_width() / src_img.get_height()
        w = int(h * aspect)

        # もし足場タイプ(kind 2)なら横に伸ばす
        if self.kind == 2:
            w = int(w * PLATFORM_STRETCH_X)

        # ガード（極端すぎないように一応）
        if w < 40:
            w = 40
        if w > 300:   # 足場はちょっと長くてもOKなので上限を広げる
            w = 300

        # スケール後の画像と当たり判定
        self.image = pg.transform.smoothscale(src_img, (w, h))
        self.rect = self.image.get_rect()

        # 出現位置
        if spawn_x is None:
            left_x = WIDTH + random.randint(0, 200)
        else:
            left_x = spawn_x
        self.rect.left = left_x
        self.rect.bottom = GROUND_Y

        self.speed = world_speed

    def update(self, world_speed: float):
        # 左方向に進む
        self.rect.x -= world_speed

        # 画面外に出たら消す
        if self.rect.right < 0:
            self.kill()

    def draw(self, surface: pg.Surface):
        surface.blit(self.image, self.rect)

    def is_stompable(self) -> bool:
        # kind 0,1 は踏んだら消える
        return self.kind in (0, 1)

    def is_platform(self) -> bool:
        # kind 2 は踏んだら乗れる
        return self.kind == 2


class Score:
    """
    スコア表示
    """
    def __init__(self, font: pg.font.Font, car: Car, car_img: pg.Surface):            
        self.font = font
        self.value = 0
        self.multiplier = 1.0
        self.color = TEXT_COLOR
        self.pos = (20, 20)
        self.friends = []  # 仲間キャラクターを管理するリスト
        self.car = car
        self.car_img = car_img  # 車画像も保持

    def set(self, v: int):
        self.value = v

    def add(self, delta: int):
        self.value += delta

    def draw(self, screen: pg.Surface):
        img = self.font.render(f"SCORE: {self.value}", True, self.color)
        screen.blit(img, self.pos)
    def add(self, points):
        self.value += int(points * self.multiplier)
    def bonus(self, kind):
        if kind == "obstacle_break":
            self.add(100)
        elif kind == "life_up":
            self.add(200)
    def update_friends(self, key_lst):
        for friend in self.friends:
            friend.update(key_lst)

    def draw_friends(self, screen):
        for friend in self.friends:
            friend.draw(screen)
    def check_for_friends(self):
        """スコアが一定を超えたら仲間を追加"""
        if self.value >= 2000 and len(self.friends) == 0:  # 2000点以上で仲間追加
            print("新しい仲間が登場！")
            new_friend = FriendCar(self.car_img, self.car.rect.left - 100, GROUND_Y,self.car)
            self.friends.append(new_friend)
        if self.value >= 5000 and len(self.friends) == 1:  # 5000点以上で次の仲間追加
            print("2人目の仲間が登場！")
            new_friend2 = FriendCar(self.car_img, self.car.rect.left - 200, GROUND_Y,self.car)
            self.friends.append(new_friend2) 

class FriendCar(Car):
    """
    仲間の車（プレイヤーの後ろに追従する車）
    """
    def __init__(self, car_img: pg.Surface, spawn_x: int, spawn_y: int, target_car:Car):
        super().__init__(car_img)  # 親クラスのCarを初期化
        self.rect.left = spawn_x    # プレイヤーの後ろに配置
        self.rect.bottom = spawn_y
        self.target_car = target_car  # 追従対象を保持

    def update(self, key_lst: list[bool]):
        super().update(key_lst)  # 親クラスのupdateを呼び出してジャンプ・重力を適用
        # 友達の車はプレイヤーを追いかける動きにする
        self.rect.x = self.target_car.rect.left - 100  # プレイヤーの後ろに追従


def get_support_y(car_rect: pg.Rect, obstacles: pg.sprite.Group) -> int:
    """
    車が今フレーム「どこを床として扱えるか」を計算して返す。
    - デフォは地面(GROUND_Y)
    - kind 2（足場タイプ）の障害物が真下にあれば、そいつの天面を床にする

    ここでいう「真下」は:
    ・水平に少しでもかぶってる（x方向で重なってる）
    ・車の足( bottom ) がその障害物の天面より上かほぼ同じ高さ（=上にいる）
    """
    support_y = GROUND_Y
    for obs in obstacles:
        if not getattr(obs, "is_platform", None):
            continue
        if not obs.is_platform():
            continue

        # 横方向の重なりチェック
        horizontal_overlap = (
            car_rect.right > obs.rect.left and
            car_rect.left < obs.rect.right
        )

        # 車がその障害物の「上側」にいるか
        above_top = car_rect.bottom <= obs.rect.top + 5

        if horizontal_overlap and above_top:
            # より高い位置（画面上側）を優先して床にする
            if obs.rect.top < support_y:
                support_y = obs.rect.top

    return support_y


def main():
    pg.init()
    pg.display.set_caption("CAR RUN (マリオ床ver)")
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    clock = pg.time.Clock()

    # ===== フォントの用意 =====
    FONT_NAME = "Meiryo"
    font_big = pg.font.SysFont(FONT_NAME, 64)
    font_small = pg.font.SysFont(FONT_NAME, 32)

    # ===== 背景画像のロード =====
    bg_img_raw = pg.image.load("fig/hai3.jpg").convert()

    # 高さに合わせてリサイズ
    base_h = HEIGHT
    base_w = int(bg_img_raw.get_width() * (base_h / bg_img_raw.get_height()))

    # 横方向だけさらに伸ばす倍率（背景をワイドに）
    HORIZ_STRETCH = 1.5
    wide_w = int(base_w * HORIZ_STRETCH)
    wide_h = base_h

    bg_img = pg.transform.smoothscale(bg_img_raw, (wide_w, wide_h))
    bg_img_flip = pg.transform.flip(bg_img, True, False)

    # ===== 車と障害物の画像ロード =====
    raw_car = pg.image.load("fig/3.png").convert_alpha()
    car_img = pg.transform.smoothscale(raw_car, (CAR_W, CAR_H))

    # 障害物3種類
    raw_obst1 = pg.image.load("fig/4.png").convert_alpha()       # stompで消えるタイプ
    raw_obst2 = pg.image.load("fig/5.png").convert_alpha()       # stompで消えるタイプ
    raw_obst3 = pg.image.load("fig/bush2.jpg").convert_alpha()   # 乗れる足場タイプ
    obstacle_image_list = [raw_obst1, raw_obst2, raw_obst3]

    # ===== ゲーム状態の初期化 =====
    car = Car(car_img)
    obstacles = pg.sprite.Group()

    world_speed = SPEED_START            # 現在のスクロール速度
    floor_scroll_x = 0.0                 # 床タイルのスクロール用オフセット
    bg_scroll_x = 0.0                    # 背景スクロール用オフセット
    start_ticks = pg.time.get_ticks()    # 開始時刻(ms)
    score_obj = Score(font_small, car,car_img)

    game_active = True
    death_time = None  # ゲームオーバーになった瞬間の時刻(ms)

    # 障害物を一定間隔で出すためのイベントタイマー
    SPAWN_EVENT = pg.USEREVENT + 1
    pg.time.set_timer(SPAWN_EVENT, SPAWN_INTERVAL_MS)

    tmr = 0  # フレームカウンタ

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
                obstacles.add(Obstacle(obstacle_image_list, world_speed))

        # ===== ロジック更新 =====
        if game_active:
            # 経過時間(秒)
            elapsed_sec = (pg.time.get_ticks() - start_ticks) / 1000.0

            # スクロール速度をじわじわ上げる
            world_speed = SPEED_START + SPEED_ACCEL * elapsed_sec

            # 背景と床のスクロール更新（左に流す）
            bg_scroll_x     -= world_speed
            floor_scroll_x  -= world_speed

            # まず障害物を動かす（今フレームの位置を確定させる）
            obstacles.update(world_speed)

            # 次に「いまどこを床にできるか？」を判定してから
            # その床を使って車を動かす
            car.floor_y = get_support_y(car.rect, obstacles)
            car.update(key_lst)

            # ===== 当たり判定＆処理 =====
            side_hit = False
            stomped_obstacles = []

            for obs in obstacles:
                if car.rect.colliderect(obs.rect):

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
                    else:
                        # 横や下から当たった → ゲームオーバー
                        side_hit = True

            # 踏みつぶした敵はまとめて消す
            for obs in stomped_obstacles:
                obs.kill()

            if side_hit:
                game_active = False
                death_time = pg.time.get_ticks()

            # ===== スコア更新（時間ベースも反映）=====
            time_score = int((pg.time.get_ticks() - start_ticks) / 10)
            if score_obj.value < time_score:
                score_obj.set(time_score)
            # スコア更新（1/100秒単位くらい）
            score_val = int((pg.time.get_ticks() - start_ticks) / 10)
            score_obj.set(score_val)
        
            # 車の更新のあと、仲間キャラクターも更新
            score_obj.update_friends(key_lst)

            # 描画時
            score_obj.draw_friends(screen)



             # 仲間キャラクターの追加チェック
            score_obj.check_for_friends()   # ← 毎フレーム呼ぶだけ      

        else:
            # ゲームオーバー後：5秒経ったら自動終了
            if death_time is not None:
                if pg.time.get_ticks() - death_time >= GAMEOVER_EXIT_DELAY_MS:
                    pg.quit()
                    sys.exit()

        # ===== 描画 =====
        # 背景（ミラー連結してスクロール）
        draw_bg_scroll(screen, bg_img, bg_img_flip, bg_scroll_x)

        # 床タイル（スクロール済みオフセットで描画）
        draw_floor_tiles(screen, floor_scroll_x)

        # プレイヤー車
        car.draw(screen)

        # 障害物
        for obs in obstacles:
            obs.draw(screen)

        # スコア
        score_obj.draw(screen)

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
