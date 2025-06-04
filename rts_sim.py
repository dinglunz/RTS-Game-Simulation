import sys
import json
import math
import argparse
import colorsys
import pygame
from collections import defaultdict


class UnitType:
    def __init__(self, health, move_speed, weapon_range, weapon_damage, weapon_cooldown):
        self.max_health = health
        self.move_speed = move_speed
        self.weapon_range = weapon_range
        self.weapon_damage = weapon_damage
        self.weapon_cooldown = weapon_cooldown


class Unit:
    def __init__(self, type_name, team_name, x, y, unit_types_dict):
        self.type_name = type_name
        self.team_name = team_name
        self.x = float(x)
        self.y = float(y)

        ut = unit_types_dict[type_name]
        self.health = float(ut.max_health)
        self.move_speed = float(ut.move_speed)
        self.weapon_range = float(ut.weapon_range)
        self.weapon_damage = float(ut.weapon_damage)
        self.weapon_cooldown = float(ut.weapon_cooldown)
        self.last_attack_time = -1e9

    def is_alive(self):
        return self.health > 0

    def distance_to(self, other_unit):
        dx = self.x - other_unit.x
        dy = self.y - other_unit.y
        return math.hypot(dx, dy)

    def move_toward_origin(self, dt):
        # If already at origin, do nothing
        if abs(self.x) < 1e-6 and abs(self.y) < 1e-6:
            return
        # Compute direction vector to origin
        dist = math.hypot(self.x, self.y)
        if dist < 1e-6:
            return
        
        step = self.move_speed * dt # Distance can move in 1 frame
        if step >= dist: # set to origin
            self.x = 0.0
            self.y = 0.0
        else:
            # Move fraction of the vector
            ratio = step / dist
            self.x -= self.x * ratio
            self.y -= self.y * ratio


def generate_team_colors(teams):
    team_list = sorted(teams)
    colors = {}

    T = len(team_list)
    for i, team in enumerate(team_list):
        hue = i / max(1, T)
        r_f, g_f, b_f = colorsys.hsv_to_rgb(hue, 1.0, 0.5)
        r = int(r_f * 255)
        g = int(g_f * 255)
        b = int(b_f * 255)
        colors[team] = (r, g, b)

    return colors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json")
    args = parser.parse_args()

    with open(args.input_json, "r") as f:
        data = json.load(f)

    # Parse unit types
    unit_types_raw = data.get("units", {})
    if not unit_types_raw:
        print("ERROR: 'units' key is missing or empty.")
        sys.exit(1)

    unit_types = {}
    for type_name, stats in unit_types_raw.items():
        try:
            ut = UnitType(
                health=stats["health"],
                move_speed=stats["moveSpeed"],
                weapon_range=stats["weaponRange"],
                weapon_damage=stats["weaponDamage"],
                weapon_cooldown=stats["weaponCooldown"],
            )
        except KeyError as e:
            print(f"ERROR: Missing field {e} for unit type '{type_name}'")
            sys.exit(1)
        unit_types[type_name] = ut

    # Parse teams and instantiate Unit objects
    teams_raw = data.get("teams", {})
    if not teams_raw:
        print("ERROR: 'teams' key is missing or empty.")
        sys.exit(1)

    units = []
    for team_name, members in teams_raw.items():
        for member in members:
            try:
                name = member["name"]
                x = member["x"]
                y = member["y"]
            except KeyError as e:
                print(f"ERROR: Missing field {e} for a member of team '{team_name}'")
                sys.exit(1)
            if name not in unit_types:
                print(f"ERROR: Unknown unit type '{name}' in team '{team_name}'")
                sys.exit(1)
            u = Unit(type_name=name, team_name=team_name, x=x, y=y, unit_types_dict=unit_types)
            units.append(u)

    # Set up pygame window
    pygame.init()
    pygame.font.init()
    WINDOW_SIZE = 800
    screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE))
    pygame.display.set_caption("RTS Game Simulation")
    clock = pygame.time.Clock()

    font_size = 16
    font = pygame.font.SysFont(None, font_size)

    max_abs = 0.0
    for u in units:
        max_abs = max(max_abs, abs(u.x), abs(u.y))
    
    padding = 0.1 * max_abs
    world_extent = max_abs + padding

    pixels_per_unit = (WINDOW_SIZE / 2) / world_extent

    def world_to_screen(wx, wy):
        """Convert world (x,y) into screen (sx,sy). Y is inverted for screen coords."""
        sx = WINDOW_SIZE / 2 + wx * pixels_per_unit
        sy = WINDOW_SIZE / 2 - wy * pixels_per_unit
        return int(sx), int(sy)

    # Assign team colors
    colors = generate_team_colors(teams=teams_raw.keys())

    damage_stats = defaultdict(float)

    # Simulation loop
    simulation_running = True

    # Fixed time step to make simulation deterministic
    FIXED_DT = 1.0 / 60.0
    frame_counter = 0

    while simulation_running:
        _ = clock.tick(60)
        dt = FIXED_DT
        current_time = frame_counter * FIXED_DT
        frame_counter += 1

        # Handle quit game
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

        alive_units = [u for u in units if u.is_alive()] # list of alive units each frame

        # Check termination
        teams_still_alive = set(u.team_name for u in alive_units)
        if len(teams_still_alive) <= 1:
            # Simulation over
            simulation_running = False
            winner = next(iter(teams_still_alive)) if teams_still_alive else None
        else:
            # Actions for each unit
            for u in alive_units:
                if not u.is_alive():
                    continue

                # Find nearest enemy
                nearest_enemy = None
                nearest_dist = float("inf")
                for other in alive_units:
                    if other.team_name == u.team_name:
                        continue
                    d = u.distance_to(other)
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest_enemy = other

                # Attack (If in weapon range)
                if nearest_enemy is not None and nearest_dist <= u.weapon_range:
                    if current_time - u.last_attack_time >= u.weapon_cooldown:
                        nearest_enemy.health -= u.weapon_damage # deal damage
                        damage_stats[u.type_name] += u.weapon_damage
                        u.last_attack_time = current_time
                else: # Move toward origin
                    u.move_toward_origin(dt)

        # Rendering
        bg_color = (40, 40, 40)
        axis_color = (80, 80, 80)
        screen.fill(bg_color)

        # Draw axis
        sx, sy = world_to_screen(0, 0)
        pygame.draw.line(screen, axis_color, (sx, 0), (sx, WINDOW_SIZE))
        pygame.draw.line(screen, axis_color, (0, sy), (WINDOW_SIZE, sy))
        
        for u in units:
            if not u.is_alive():
                continue
            sx, sy = world_to_screen(u.x, u.y)
            color = colors[u.team_name]
            # Draw unit
            pygame.draw.circle(screen, color, (sx, sy), 10)

            # Draw Health bar
            health_pct = max(0.0, u.health / unit_types[u.type_name].max_health)
            bar_width = 16
            bar_height = 2
            hb_x = sx - bar_width // 2
            hb_y = sy - 14
            pygame.draw.rect(screen, (100, 100, 100), (hb_x, hb_y, bar_width, bar_height))
            pygame.draw.rect(screen, (0, 200, 0), (hb_x, hb_y, int(bar_width * health_pct), bar_height))

            # Draw the capital letter of the unit type
            first_letter = u.type_name[0].upper()
            text_surface = font.render(first_letter, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=(sx, sy))
            screen.blit(text_surface, text_rect)

        pygame.display.flip()

        if not simulation_running:
            break

    # Produce result summary
    print("\n\n===== Simulation Complete =====")
    if winner is None:
        print("No units remain (tie).")
    else:
        print(f"Winning team: {winner}")

    print("\nDamage dealt per unit type:")
    for type_name in sorted(unit_types.keys()):
        dmg = damage_stats.get(type_name, 0.0)
        print(f"- {type_name}: {dmg:.2f} total damage")
    print("===============================\n\n")

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)


if __name__ == "__main__":
    main()
