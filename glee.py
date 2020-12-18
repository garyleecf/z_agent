'''
GLEE Agent

BIO:
This gleeful agent scavenges for ammo and treasures whenever they appear -- that's its priority!
But what's most important to a scavenger, of course, is its survival!
When it detects danger, it attempts to move away from impending explosions, using the expertise imparted from its human companions.

When there's nothing to scavenge, this agent goes around blowing things up...
And when there's nothing else to do, guess what's left that is worth scavenging?...
'''

# import any external packages by un-commenting them
# if you'd like to test / request any additional packages - please check with the Coder One team
import random
import time
# import numpy as np
# import pandas as pd
# import sklearn
from .utils import *
from .pathfinder import *
from .bombmapper import *

_DEBUG_PRINT = False

class Agent:
    ACTION_PALLET = ['', 'u','d','l','r','p', '']

    def __init__(self):
        self.name = "glee"
        """ Initialization
        """
        self.player_id = None
        self.opp_id = None
        self.i = 0
        self.bombmapper = BombMapper()
        self.pathfinder = PathFinding()
        self.path_plan = None
        self.bored = True
        self.plan_to_bomb = False
        self.post_bombing = False

        self.opp_prev_loc = None
        self.opp_idle = 0

        self.current_target = None

        self.current_mode = None
        self.sb_bombed = []
        self.danger_past = 0
        self.huntdown_opp = False

        self.unreachables = []

    def next_move(self, game_state, player_state):
        if self.current_mode:
            if _DEBUG_PRINT:
                print(self.current_mode)
            self.current_mode = None
        """ This method is called each time the agent is required to choose an action
        """
        if self.player_id is None:
            self.player_id = player_state.id
        player_loc = player_state.location
        opp_loc = game_state.opponents(2)[1-self.player_id]
        if self.opp_prev_loc is None:
            self.opp_prev_loc = opp_loc
        if game_state.tick_number - self.i > 1:
            if _DEBUG_PRINT:
                print(f'Tick {game_state.tick_number}: {game_state.tick_number-self.i}')
        self.i = game_state.tick_number


        self.bombmapper.update(game_state)
        valid_actions, game_map = get_valid_actions(game_state,player_state)


        ####################
        # Danger Check and Evasion Maneuveur:
        ####################
        # On the safe side: avoid blast radius for 3 ticks
        self.danger_past -= 1
        in_danger = self.danger_past > 0
        for b in game_state.bombs:
            if hamming_dist(b, player_loc) <= 4:
                if self.bombmapper.explosion_map(game_state)[b] < 6:
                    in_danger = True
                    self.danger_past = 3
                    break
        if in_danger or self.post_bombing:
            self.current_mode = 'Evading' if in_danger else 'AfterBomb'
            # Ditch whatever plan
            self.path_plan = []
            self.bored = True
            self.post_bombing = False

            exp_map = self.bombmapper.explosion_map(game_state)
            value = neighbor_tile_values(game_state, player_loc, 1-self.player_id, game_map, exp_map)
            if _DEBUG_PRINT:
                print(value)
            movement_options = ['l','r','u','d', '']
            action_id = random.choice([i for i, v in enumerate(value) if v==np.nanmax(value)])
            return movement_options[action_id]


        ####################
        # Exploit Idling Opponent:
        ####################
        # If opponent has been idle, plant bombs beside
        if hamming_dist(opp_loc, self.opp_prev_loc)==0:
            self.opp_idle += 1
            if self.opp_idle >= 3 and hamming_dist(player_loc, opp_loc)==1:
                self.current_mode = 'Exploit Idling'
                if player_state.ammo:
                    self.post_bombing = True
                    return 'b'
        else:
            self.opp_prev_loc = opp_loc
            self.opp_idle = 0


        ####################
        # Find next plan:
        ####################
        # Find Ammo or Treasure (prioritise ammo)
        new_target_pos = closest_object(player_loc, game_state.ammo+game_state.treasure, self.unreachables)
        if new_target_pos is None:
            self.unreachables = []
        if (game_state.ammo or game_state.treasure) and (self.bored or hamming_dist(new_target_pos, player_loc) < hamming_dist(self.current_target, player_loc)):
            # target_pos = closest_object(player_loc, game_state.ammo+game_state.treasure)
            target_pos = new_target_pos
            # problem: closest object may not be reachable
            path, path_found = self.pathfinder.search(player_loc, target_pos, game_state, 1, occupied_blocktypes=['sb', 'ib', 'ob', 'b'])
            if path_found:
                self.path_plan = path
                self.bored = False
                self.current_target = target_pos
                self.current_mode = 'Ammo/Treasure Hunting'
            else:
                self.unreachables.append(target_pos)

        easy_ore_available, easy_ore_list = check_ore_blocks(game_state)
        if easy_ore_available and player_state.reward > 7:
            if game_state.ore_blocks and self.bored and player_state.ammo > 0:
                for easy_ob in easy_ore_list:
                    target_pos = easy_ob
                    if hamming_dist(target_pos, player_loc) > 1:
                        path, path_found = self.pathfinder.search(player_loc, target_pos, game_state, 1, occupied_blocktypes=['sb', 'ib', 'ob', 'b'])
                        if path_found:
                            self.path_plan = path
                            self.bored = False
                            self.plan_to_bomb = True
                            self.current_mode = 'Easy Ore Block Bombing'
                            break

        if game_state.soft_blocks and self.bored and player_state.ammo > 0:
            target_pos = closest_object(player_loc, game_state.soft_blocks, self.sb_bombed)
            checked = [target_pos]
            path_found = False
            while len(checked) < len(game_state.soft_blocks):
                if hamming_dist(target_pos, player_loc) > 1:
                    path, path_found = self.pathfinder.search(player_loc, target_pos, game_state, 1, occupied_blocktypes=['sb', 'ib', 'ob', 'b'])
                    if path_found:
                        self.path_plan = path
                        self.bored = False
                        self.plan_to_bomb = True
                        self.current_mode = 'Soft Block Bombing'
                        break
                target_pos = closest_object(player_loc, game_state.soft_blocks, self.sb_bombed+checked)
                checked.append(target_pos)

        if game_state.ore_blocks and self.bored and player_state.ammo > 0:
            target_pos = closest_object(player_loc, game_state.ore_blocks)
            if hamming_dist(target_pos, player_loc) > 1:
                path, path_found = self.pathfinder.search(player_loc, target_pos, game_state, 1, occupied_blocktypes=['sb', 'ib', 'ob', 'b'])
                if path_found:
                    self.path_plan = path
                    self.bored = False
                    self.plan_to_bomb = True
                    self.current_mode = 'Ore Block Bombing'


        if self.bored or self.huntdown_opp:
            path, path_found = self.pathfinder.search(player_loc, opp_loc, game_state, 1)
            if path_found:
                self.path_plan = path
                self.current_mode = 'Hunter'
            self.huntdown_opp = False


        ####################
        # Follow that plan:
        ####################
        # If there is a plan, follow that plan
        if self.path_plan:
            if self.path_plan[0]==player_loc:
                self.path_plan.pop(0)

            if self.path_plan:
                next_pos = self.path_plan[0]
                path_action = ''
                if game_state.entity_at(next_pos) in ['sb', 'ob']:
                    if self.plan_to_bomb:
                        self.current_mode = 'Boom'
                        path_action = 'b'
                        self.post_bombing = True
                        self.plan_to_bomb = False
                        if game_state.entity_at(next_pos) == 'sb':
                            self.sb_bombed.append(next_pos)
                        return path_action
                elif game_state.entity_at(next_pos) in ['b']:
                    self.path_plan = []
                else: # Movement
                    if next_pos[0] - player_loc[0] == 0:
                        if next_pos[1] > player_loc[1]:
                            path_action = 'u'
                        if next_pos[1] < player_loc[1]:
                            path_action = 'd'
                    else:
                        if next_pos[0] > player_loc[0]:
                            path_action = 'r'
                        if next_pos[0] < player_loc[0]:
                            path_action = 'l'
                    return path_action


        # No more moves left in plan
        if not self.path_plan or (game_state.entity_at(self.path_plan[0]) in ['ib', 'sb', 'ob', 'b', 1-self.player_id] and game_state.entity_at(player_loc) == 'b'):
            self.current_mode = 'Nothing to do'
            # self.sb_bombed = []
            # self.unreachables = []
            if self.post_bombing:
                self.huntdown_opp = True
            self.bored = True

            next_action = ''
            path, path_found = self.pathfinder.search(player_loc, opp_loc, game_state, 1)
            if path_found:
                self.path_plan = path

            exp_map = self.bombmapper.explosion_map(game_state)
            value = neighbor_tile_values(game_state, player_loc, 1-self.player_id, game_map, exp_map)
            if _DEBUG_PRINT:
                print(value)
            movement_options = ['l','r','u','d', '']
            action_id = random.choice([i for i, v in enumerate(value) if v==np.nanmax(value)])
            next_action = movement_options[action_id]

            return next_action


        # player_loc = player_loc
        # map_array
        # self.bombmapper.timeleft()

        #  # Lets pretend that agent is doing some thinking
        # # time.sleep(1)
        # print(array_to_str(self.bombmapper.neighborhood_bomb(player_loc, game_state, grid_radius=2)))
        # self.bombmapper.neighborhood_bomb(player_loc, game_state, grid_radius=2)

        # #
        # print(neighborhood_array(game_state, player_loc, grid_radius=2, match_gui=True))
        self.current_mode = 'End of Loop'
        return ''#'p' if self.i%2 else 'u'
