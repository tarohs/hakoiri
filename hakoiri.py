#
# hakoiri.py:
#   Hakoiri Musume - sliding block puzzle (klotskie type) solver
#   find answer with both optimal steps/RLC (rectlinear count)
#
# (c) SASAKI, Taroh (sasaki.taroh@gmail.com)
#
# 2025. 6.24-27: ver 0.1: (initial version)
#             only rectangular blocks, optimal step count, vertical search
# 2025. 6.28: ver 0.2: change to horizontal search (BFS)
# 2025. 6.29: ver 0.3: paralellized
# 2025. 7. 1: (first ans for hakoiri-diff (iMac pro) got)
# 2025. 7. 4: ver 0.4: RLC optimize in the "best step"
#             (not enough, worked on Conway's century & +50 however)
# 2025. 7. 5: ver. 1.0: type annoted, var name unified
#             BFS, multiprocess, 
# 2025. 7. 7: ver. 1.1: stop using Move/Coords struct for speed
# 2025. 7. 8: ver. 1.2: koma definitions by XML,
#             separated modules for common config & read XML,
#             many global vars to hand to child in args,
#             select best ans & print goal on parent
# 2025. 7. 9: ver. 1.3: argpars added,
#             defined Puzzle struct to summarize puzzle definitions,
#             koma check (& -c option) added
# 2025. 7.10: (ans for hakoiri-diff got by MBP)
# 2025. 7.12: ver. 2.0: (del() per process fork failed,) del() after fork,
#             data structure improved: MPR (tosearch) dic->list->tuple,
#             movehist list->tuple
# 2025. 7.13: ver. 2.1: Bmatrix improved: on search on same board,
#             erase->search->draw instead of creating new object
#             (& extend for non-rect shape)
# 2025. 7.15: ver. 2.2: Coords be int: (y << 4 | x)
# 2025. 7.15: ver. 2.3: Bmatrix changed from np.ndrray to int[] (bitmap)
#             (MPR name chaned to MCR: Movehist, *Colist*, RLC)
# 2025. 7.16: (ver. 3.0: searched on Scr "sorted class list" to avoid sort,
#              but not fast)
# 2025. 7.16: (ver. 3.0: searched on Scr "sorted class list" to avoid sort,
#              but not fast)
# 2025. 7.16: (ver. 2.4: Move to be int, but not fast on big model)
# 2025. 7.17: (ver. 2.5: tried to avoid mirror hash, but slowed)
# 2025. 7.17: ver. 2.6: (funcname/varname/type changed, let mypy quiet)
# 2025. 7.20: ver. 4.0: added optimal RLC search ((<-- branch of 2.6))
# 2025. 7.20-23: ver. 4.1: logic fix: RL move donot stop with in-med memo
#                       reference, + avoid perpetual loop in 1 RL move
# 2025. 7.28: ver. 4.2: can define non-rectanguler koma (numpy unused)
# 2025. 7.29: ver. 4.3: (readpuzzle.py) automatically separate komaclass
#                       when goaltype == BYID and goal koma has the same
#                       class komas (tested w/Chicagos and Superdries).
#                       change to BYID when BYCLS and all goal koma are
#                       unique in their classes
# 2025. 7.30: ver. 4.4: add koma check for all 0 row/column,
#                       ismirrorident auto switch off if non-symmetric
#                       koma exists
# 2025. 8. 1: ver. 4.5: options to be struct
version = '4.5'
#
# articles:
#   (Part I):  https://zenn.dev/taroh/articles/2703c914dd6597
#   (Part II): https://zenn.dev/taroh/articles/80874e761c18d7
#

#import numpy as np
import copy
import sys
import time
import concurrent.futures
import multiprocessing
#from collections import deque
#from collections import ChainMap
from typing import NewType, Optional
import argparse

import hakocom as hi
from hakocom import Coords, \
    Komaid, Komacls, Colist, Codict, Schash, Sclist, Dirid, \
    Move, Movehist, Rlc, Bmatrix, \
    Goaltype, Mcr, \
    Puzzle, Options
from hakocom import cox, coy, co2yx, yx2co
import readpuzzle as rx


#........................................................................
# global in main module
timer: float

#------------------------------------------------------------------------
def monitor(message: object) -> None:
# comment out if debug run
#    print(message)
    return


def main() -> None:
    # set by getoptoins()
    opts = getoptions()
    puzzle = rx.readxml(opts)
    hi.printoptions(opts)
    hi.printpuzzle(puzzle)
    monitor(puzzle)
    if opts.ischeckonly:
        sys.exit(0)
    hakosearch(puzzle, opts)
    print('@answer not found')
    sys.exit(1)


def getoptions() -> Options:
    opts = Options()
    parser = argparse.ArgumentParser(
        description = 'hakoiri-musume (sliding block puzzle) solver',
        epilog = 'hakoiri.py ' + str(version) + \
                 ' (c) 2025 by taroh (sasaki.taroh@gmail.com)')
    parser.add_argument('PUZZLENAME')
    parser.add_argument('-p', '--paralell', action = 'store_true',
                        help = 'paralell search')
    parser.add_argument('-n', '--nonparalell', action = 'store_true',
                        help = 'non paralell search')
    parser.add_argument('-r', '--optrlc', action = 'store_true',
                        help = 'optimize for RLC (rectlinear count)')
    parser.add_argument('-t', '--optsteps', action = 'store_true',
                        help = 'optimize for steps')
    parser.add_argument('-s', '--stopsteps', metavar = 'N', type = int,
                        default = -1,
                        help = 'stop at N steps')
    parser.add_argument('-x', '--maxnprocs', metavar = 'N', type = int,
                        default = 10,
                        help = 'maximum # child processes')
    parser.add_argument('-d', '--minnsearchdiv', metavar = 'N', type = int,
                        default = 200,
                        help = 'minimum # candidates in a division (child)')
    parser.add_argument('-c', '--checkonly', action = 'store_true',
                        help = 'check koma and print init/goal only')
    parser.add_argument('-v', '--version', action = 'version',
                        version = '%(prog)s ' + version)
    args = parser.parse_args()
    opts.filename = args.PUZZLENAME
    opts.isparalell = True
    if args.paralell:
        if args.nonparalell:
            hi.errorstop('cannot specify both --paralell and --nonparalell')
#        else:
#            opts.isparalell = True
    elif args.nonparalell:
        opts.isparalell = False
    opts.isoptrlc = False
    if args.optrlc:
        if args.optsteps:
            hi.errorstop('cannot specify both --optrlc and --optsteps')
        else:
            opts.isoptrlc = True
#    elif args.optsteps:
#        opts.isoptrlc = False
    opts.stopsteps = args.stopsteps
    opts.maxnprocs = args.maxnprocs
    opts.minnsearchdiv = args.minnsearchdiv
    opts.ischeckonly = args.checkonly

    return opts


#........................................................................
def hakosearch(puzzle: Puzzle, opts: Options) -> None:
    '''
    (paralell) horizontal search
    '''
    timer = time.time()
    memoschash: set[Schash] = set()
    # put the init pos in memo
    memoschash.add(hi.hashcolist(puzzle, Colist(puzzle.initcolist)))
    step = 0
    if opts.isoptrlc:
        startrlc = Rlc(0)
    else:
        startrlc = Rlc(1)
        # (in optstep search, not increased in step 1)
    tosearch: list[Mcr] = [Mcr(Movehist((Move((Komaid(0), Dirid(0))), )),
                               Colist(puzzle.initcolist), startrlc)]
    if opts.isoptrlc:
        childfunc = hakochild_optrlc
        stepstr = 'RLC'
    else:
        childfunc = hakochild_optsteps
        stepstr = 'step'
    while 0 < (nsearch := len(tosearch)):
        if nsearch <= opts.maxnprocs * opts.minnsearchdiv:
            nprocs = (nsearch + opts.minnsearchdiv - 1) // opts.minnsearchdiv
            nsearchdiv = opts.minnsearchdiv
        else:
            nprocs = opts.maxnprocs
            nsearchdiv = nsearch // opts.maxnprocs
        if opts.isparalell and 1 < nprocs:
            print(
                f'---(p{nprocs}){stepstr}: {step}, cand: {len(tosearch)}, ' +
                f'time: {time.time() - timer}, memo: {len(memoschash)}'
            )
            nextsearch: dict[Schash, Mcr] = dict()
            st = 0
            futures = []
            foundans: list[Mcr] = []
            with concurrent.futures.ProcessPoolExecutor(
#                    max_workers = MAXWORKERS
                 ) as executor:
#            with concurrent.futures.ProcessPoolExecutor(
#                    max_workers = nprocs) as executor:
#            with concurrent.futures.ThreadPoolExecutor() as executor:
                for pn in range(nprocs):
                    if pn < nprocs - 1: 
                        ed = st + nsearchdiv
                    else:
                        ed = nsearch
                    futures.append(
                        executor.submit(childfunc, puzzle,
                                        tosearch[st:ed], memoschash)
                    )
                    st = ed
                del(tosearch[:])
                for future in concurrent.futures.as_completed(futures):
                    try:
                        fachild, nschild = future.result()
                    except Exception as e:
                        print(f'error in task: {e}')
                        sys.exit(11)
                    foundans += fachild
## to ignore optimal #steps on optrlc search:
##   or optimal #rectlinear-counts on optsteps search (force update)
#                    nextsearch.update(nschild)
                    if opts.isoptrlc:
# take account of optimal #steps on optrlc search:
                        for schash, mcr in nschild.items():
                            if not schash in nextsearch or \
                               len(mcr.movehist) < \
                                            len(nextsearch[schash].movehist):
                                nextsearch[schash] = mcr
                            #if not schash in nextsearch:
                            #    nextsearch[schash] = mcr
                            #elif len(mcr.movehist) < \
                            #                len(nextsearch[schash].movehist):
                            #    print('+', end = '')
                            #    nextsearch[schash] = mcr
                    else:
# take account of optimal #rectlinear-counts on optsteps search: (note A)
                        for schash, mcr in nschild.items():
                            if not schash in nextsearch or \
                               mcr.rlc < nextsearch[schash].rlc:
                                nextsearch[schash] = mcr
                            elif mcr.rlc == nextsearch[schash].rlc:
                                kid = mcr.movehist[-1][0]
                                bmx = hi.makebmatrix(puzzle, mcr.colist,
                                                     xkoma = kid)
                                if cancontigmove(puzzle, bmx, mcr.colist,
                                                 mcr.movehist[-1]):
                                    nextsearch[schash] = mcr
# note A:
#  optimal rectilinear steps is the problem of
#  keep/override dict when different value with same key comes:
#  theoretically, not affecting the optimal "steps."
# ex. 1: the same 4 steps but
#         move 1    move 2
# step 0: . . A B   . . A B
#      1: . A . B   . A . B
#      2: A . . B   . A B .
#      3: A . B .   A . B .
#      4: A B . .   A B . .
#         (2 rlc)   (4 rlc) *rlc = rectlinear moves
# move 1 comes first, then move 2 overrides dict
# when we don't take account of optimal rectlinear steps.

# ex. 2: the same 3 steps, same 2 rlc until step 2:
#         move 1    move 2
# step 0: . B ? ?   . B ? ?
#         A . X X   A . X X
#
# step 1: . B ? ?   A B ? ?
#         A X X .   . . X X
#
# step 2: A B ? ?   A B ? ?
#         . X X .   . X X .
# -> cancontigmove()
#         (A)False  (X)True
#
# step 3: A B ? ?   A B ? ?
#         X X . .   X X . .
#         (3 rlc)   (2 rlc)
# at step 2, the same rlc must be compared by
# "if the same koma can move in next step"
# (move 1 cannot, move 2 can - so we take move 2).
# move 1 comes first then move 2 overrides.
# move 2 comes first, then move 1 don't override.
# * I don't confirm whether 1 step look aheard is enough:
#   if both the move in dic and overriding move is contigurous move
#   (always overrides), >= 2 steps after may not be the optimal rlc.

        else:
            print(
                f'---{stepstr}: {step}, cand: {len(tosearch)}, ' +
                f'time: {time.time() - timer}, memo: {len(memoschash)}'
            )
            foundans, nextsearch = childfunc(puzzle, tosearch, memoschash)
        memoschash |= set(nextsearch.keys())
        if 0 < len(foundans):
            print(
                f'---after {stepstr}: {step}, cand: {len(tosearch)}, ' +
                f'time: {time.time() - timer}, memo: {len(memoschash)}'
            )
            print()
            monitor(foundans)
            hi.printbestans(puzzle, foundans, Colist(puzzle.initcolist),
                            opts.isoptrlc)
            # NEVERREACHED
        if step == opts.stopsteps:
            print(opts.stopsteps, time.time() - timer)
            print('@stopped')
# candidate monitor when stop
        #    for mcr in nextsearch.values():
        #        print(f'move: {mcr.movehist}')
        #        printnamematrix(puzzle, mcr.colist)
        #        print(f'rlc: {mcr.rlc}')
            exit(3)
        del(tosearch)
        tosearch = list(nextsearch.values())
        del(nextsearch)
        step += 1
# candidate monitor by step
#        for mcr in tosearch:
#            print(f'move: {mcr.movehist}')
#            hi.printnamematrix(puzzle, mcr.colist)
#            print(f'rlc: {mcr.rlc}')
    return


def hakochild_optsteps(puzzle: Puzzle,
              tosearch: list[Mcr], memoschash: set[Schash]
             ) -> tuple[list[Mcr], dict[Schash, Mcr]]:
    '''
    returns foundans, {SCHASH: (MOVES, COLIST, RLC), ...}
    where foundans = [MCR, ...]
          SCLIST = hi.hashcolist(COLIST)
          RLC = rectlinear count in MOVES
    '''

#    monitor(f'(c)@{len(tosearch)}')
    nextsearch: dict[Schash, Mcr] = dict()
    foundans = []
    for mcr in tosearch:
        movehist = mcr.movehist
        colist = mcr.colist
        rlc = mcr.rlc
        bmx = hi.makebmatrix(puzzle, colist, Komaid(1))
        for k in range(1, puzzle.nkoma + 1):
            kid = Komaid(k)
            if kid != 1:
                hi.drawerasebmx(puzzle, puzzle.komacls[kid], colist[kid],
                                bmx, mode = 0) # erase rect
            for dn in range(4):
                dirid = Dirid(dn)
                if movehist[-1][0] == kid and \
                   (movehist[-1][1] - dirid + 4) % 4 == 2:
                    # same as last moved koma and opposite dir
                   continue
#                monitor(f'{kid} moves to {dirid}: ')
                co = Coords(colist[kid] +  hi.dirvec[dirid])
                if hi.collidep(puzzle, puzzle.komacls[kid], co, bmx):
#                    monitor('... cannot move')
                    continue
#Colist == list version
#                newcolist = Colist(copy.deepcopy(colist))
#                newcolist[kid] = Coords(co)
#Colist == tuple version
                newcolist = Colist(colist[:kid] + (co, ) + \
                                         colist[kid + 1:])
                newmovehist = Movehist(
                    movehist + (Move((kid, dirid)), ))
                newschash = hi.hashcolist(puzzle, newcolist)
                newrlc = rlc
                if 3 <= len(newmovehist) and \
                   newmovehist[-1][0] != newmovehist[-2][0]:
                    # MOVE: (KOMAID, DIRID)
                    # (after step 2) and (moved kid != last moved kid)
                    newrlc = Rlc(newrlc + 1)
                if hi.isgoal(puzzle, newcolist, newschash):  # answer found
                    foundans.append(Mcr(newmovehist, newcolist, newrlc))
                    print('@found')
                    continue
#                monitor(hi.makebmatrix(puzzle, newpos, None))
# to ignore optimal rectlinear steps:
#                if not cshash in memocshash:
#                    nextsearch[cshash] = (newmovehist, newposet)
# take account of optimal rectlinear steps: (note (A): see comments on parent)
                if not newschash in memoschash:
                    if not newschash in nextsearch or \
                       newrlc < nextsearch[newschash].rlc or \
                       (newrlc == nextsearch[newschash].rlc and \
                        cancontigmove(puzzle, bmx,
                                      newcolist, newmovehist[-1])):
                        nextsearch[newschash] = \
                            Mcr(newmovehist, newcolist, newrlc)
                        monitor(
                            f'added ({newmovehist}, {newcolist}, {newrlc}) '\
                             + f'at {newschash}')
#                else:
#                    monitor(f'... {newschash} in memo')
            # done 4 dir search
            hi.drawerasebmx(puzzle, puzzle.komacls[kid], colist[kid],
                            bmx, mode = 1)
            # draw rect, recover koma
#    monitor(f'>(c)checked {len(tosearch)}, ret {len(nextsearch)}')
#    for h, mcr in nextsearch.items():
#        print(h)
#        hi.printnamematrix(puzzle, mcr.colist)
    return foundans, nextsearch


def cancontigmove(puzzle: Puzzle, bmx: Bmatrix,
                  colist: Colist, lastmove: Move) -> bool:
    lastmkoma, lastmdir = lastmove  # (KOMAID, DIRID)
    lastco = colist[lastmkoma]
#    print(f'{lastmkoma=}, {lastmdir=}, {lastco=}')
#    print(bmx)
    for dirid in range(4):
        if (lastmdir - dirid + 4) % 4 == 2:  # opposit direction
            continue
        co = Coords(lastco + hi.dirvec[dirid])
        if not hi.collidep(puzzle, puzzle.komacls[lastmkoma], co, bmx):
            return True
    return False


def hakochild_optrlc(puzzle: Puzzle,
              tosearch: list[Mcr], memoschash: set[Schash]
             ) -> tuple[list[Mcr], dict[Schash, Mcr]]:
    '''
    returns foundans: list[Mcr],
            nextsearch: {SCHASH: (MOVES, COLIST, RLC), ...}
      where SCHASH = hi.hashcolist(COLIST)
    '''
    def contigmove(kid: Komaid, mcr: Mcr, perpet: list[Coords],
                   bmx: Bmatrix,
                   memoschash: set[Schash], nextsearch: dict[Schash, Mcr],
                   foundans: list[Mcr]
                   ) -> None:
        '''
        recursive DFS:
        try to move only (the same koma) kid until it cannot move
        or the hash(board) becomes as the same one in the momoschash.
        returns None, but appends new candidates (by pointer of nextsearch),
                                  found answer (by pointer of foundans)
                          if exist.
        '''
#        print(f'@{mcr.movehist[-1]}')
#        hi.printnamematrix(puzzle, mcr.colist)
#        for r in bmx:
#            print(bin(r)[-1:1:-1])
        movehist = mcr.movehist
        colist = mcr.colist
        rlc = mcr.rlc # is already increased if called by hakochild
                      # (not increased when called by itself)
        for dn in range(4):
            dirid = Dirid(dn)
#            if movehist[-1][0] == kid and \
#               (movehist[-1][1] - dirid + 4) % 4 == 2:
#                # same as last moved koma and opposite dir
#                continue
#            monitor(f'{kid} moves to {dirid}')
            newco = Coords(colist[kid] +  hi.dirvec[dirid])
            if newco in perpet or \
               hi.collidep(puzzle, puzzle.komacls[kid], newco, bmx):
                monitor('... cannot move or perpetual')
                continue
            newmovehist = Movehist(movehist + (Move((kid, dirid)), ))
            newcolist = Colist(colist[:kid] + (newco, ) + colist[kid + 1:])
            newschash = hi.hashcolist(puzzle, newcolist)
            if hi.isgoal(puzzle, newcolist, newschash):  # answer found
                foundans.append(Mcr(newmovehist, newcolist, rlc))
                print('@found')
                return  # only 1 ans may be found in one RL move
            if not newschash in memoschash and \
               (not newschash in nextsearch or \
                len(newmovehist) < len(nextsearch[newschash].movehist)
               ):
            #if not newschash in memoschash:
            #  if not newschash in nextsearch:
            #    nextsearch[newschash] = Mcr(newmovehist, newcolist, rlc)
            #  elif len(newmovehist) < len(nextsearch[newschash].movehist):
            #    print('.', end = '')
                nextsearch[newschash] = Mcr(newmovehist, newcolist, rlc)
#                monitor(
#                    f'added ({newmovehist}, {newcolist}, {rlc}) '\
#                    + f'at {newschash} (cont move)')
#            else:
#                monitor(f'{newschash} in memo or (in cand and not shorter) ' +
#                        '(cont move)')
            contigmove(kid, Mcr(newmovehist, newcolist, rlc), perpet + [newco],
                       bmx, memoschash, nextsearch, foundans)
        return

#    monitor(f'(c)@{len(tosearch)}')
    nextsearch: dict[Schash, Mcr] = dict()
#    for (moves, colist, rlc) in tosearch:
#    print('@@', memoschash)
    foundans: list[Mcr] = []
    for mcr in tosearch:
        bmx = hi.makebmatrix(puzzle, mcr.colist)
        mcr.rlc = Rlc(mcr.rlc + 1)
        for k in range(1, puzzle.nkoma + 1):
            kid = Komaid(k)
            if mcr.movehist[-1][0] == kid:
                # the same koma as the last doesnot move (it's optrlc)
                continue
            hi.drawerasebmx(puzzle, puzzle.komacls[kid], mcr.colist[kid],
                            bmx, mode = 0) # erase rect
            contigmove(kid, mcr, [], bmx, memoschash, nextsearch, foundans)
            hi.drawerasebmx(puzzle, puzzle.komacls[kid], mcr.colist[kid],
                            bmx, mode = 1) # draw rect, recover koma
#    monitor(f'>(c)checked {len(tosearch)}, ret {len(nextsearch)}')
#    for h, mcr in nextsearch.items():
#        print(f'{len(mcr.movehist) - 1} ({hex(h)})')
#        hi.printnamematrix(puzzle, mcr.colist)
    return foundans, nextsearch

#........................................................................
if __name__ == '__main__':
  main()
