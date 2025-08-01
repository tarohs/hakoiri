from dataclasses import dataclass, field
from typing import NewType, Optional, cast, TextIO, NoReturn
from enum import Enum, auto
#import numpy as np
import copy
import sys

Coords = NewType('Coords', int) # uint8: (YYYY XXXX)_2
## Coords are now & Coval unified (ver. 2.2)
#Coords = NewType('Coords', tuple[int, int])
#Coval = NewType('Coval', int)
## dataclasses are too heavy (ver. 1.1 obsolate)
#@dataclass
#class Coords:
#    y: int
#    x: int
##    def __add__(self, addee: Coords):
#    def __add__(self, addee):
#        return Coords(self.y + addee.y, self.x + addee.x)
#
#@dataclass
#class Koma:
#    id: int
#    nam: str
#    siz: tuple[int, int]
#    sizcls: int
#    initpos: tuple[int, int]
Komaid = NewType('Komaid', int)
Komacls = NewType('Komacls', int)
# coords of all complete koma set [None, coords#1, ..., coords #n]
# Colist == list version
#Colist = NewType('Colist', list[Optional[Coords]])
# Colist == tuple version
Colist = NewType('Colist', tuple[Coords, ...])
# coords of partial koma set {kid: coords#kid}
Codict = NewType('Codict', dict[Komaid, Coords])
# hashed value
Schash = NewType('Schash', int)
# hashed (encoded) class+coords ordered Colist
Sclist = NewType('Sclist', tuple[Coords, ...])
# Dirid is int {0, 1, 2, 3}, not enum of vector (tuple)
#   because: (1) more efficiant than tuple, (2) can know opposite dir easily
Dirid = NewType('Dirid', int)
Move = NewType('Move', tuple[Komaid, Dirid])
#@dataclass
#class Move:
#    komaid: Komaid
#    dirid: Dirid
# Movehist == list version
#Movehist = NewType('Movehist', list[Move])
# Movehist == tupple version # note: this reducts deepcopy(), super big effect
Movehist = NewType('Movehist', tuple[Move, ...])

Rlc = NewType('Rlc', int)
Bmatrix = NewType('Bmatrix', list[int])

@dataclass
class Mcr:
    movehist: Movehist
    colist: Colist
    rlc: Rlc

class Goaltype(Enum):
    BYID = auto()
    BYCLS = auto()
    BYCLSHASH = auto()

@dataclass
class Puzzle:
    name: str = ''
    bsize: Coords = Coords(0)
    extwall: list[Coords] = field(default_factory = list)
    ismirrorident: bool = True
    clssiz: list[Coords] = field(default_factory = list)
    clsshape: list[list[int]] = field(default_factory = list)
    clsnam: list[str] = field(default_factory = list)
    nkoma: int = 0
    goaltype: Goaltype = Goaltype.BYID
    komacls: list[Komacls] =  field(default_factory = list)
    komanam: list[str] = field(default_factory = list)
    komanamshort: list[str] = field(default_factory = list)
    initcolist: tuple[Coords, ...] = field(default_factory = tuple)
    # one of the below 3 is valid:
    goal_koma: list[tuple[Komaid, Coords]] \
        = field(default_factory = list[tuple[Komaid, Coords]])
    # all komas (class compatible) reaches their goals
    goal_schash: Schash = Schash(0)

@dataclass
class Options:
    filename: str = ''
    stopsteps: int = -1
    isoptrlc: bool = False
    isparalell: bool = True
    maxnprocs: int = 10
    minnsearchdiv: int = 200
    ischeckonly: bool = False


# some global constants
#dirvec = [Coords((-1, 0)), Coords((0,  1)),
#          Coords(( 1, 0)), Coords((0, -1))]
dirvec = [Coords(-(1 << 4)), Coords( 1),
          Coords(  1 << 4) , Coords(-1)]
dirname = ['N', 'E', 'S', 'W']
CLS_WALL = Komacls(99)

#------------------------------------------------------------------------
# functions
#
# short funcs
#
def coy(co: Coords) -> int:
    return co >> 4 & 0x0f
def cox(co: Coords) -> int:
    return co & 0x0f
def co2yx(co: Coords) -> tuple[int, int]:
    return ((coy(co), cox(co)))
def yx2co(yx: tuple[int, int]) -> Coords:
    y, x = yx
    return Coords(y << 4 | x)

#
# cooreds & hash functions
#
def comirror(co: Coords, komawidth: int, boardwidth: int) -> Coords:
    ys, x = co & 0xf0, co & 0x0f
    mx = (boardwidth - 1 - x) - (komawidth - 1)
    return Coords(ys | mx)

def hashcolist(puzzle: Puzzle, colist: Colist) -> Schash:
    def clssort(colist: Colist, ismirror: bool) \
            -> Sclist:
        if not ismirror:
            clscoval = [(puzzle.komacls[kid], colist[kid])
                        for kid in range(1, puzzle.nkoma + 1)]
        else:
            clscoval = [(puzzle.komacls[kid],
                         comirror (colist[kid],
                                   cox(puzzle.clssiz[puzzle.komacls[kid]]),
                                   cox(puzzle.bsize))
                         ) for kid in range(1, puzzle.nkoma + 1)]
        cosorted = sorted(sorted(clscoval, key = lambda x: x[1]),
                          key = lambda x: x[0])
        return Sclist(tuple(v for k, v in cosorted))

    def comirror(co: Coords, komawidth: int, boardwidth: int) -> Coords:
        ys, x = co & 0xf0, co & 0x0f
        mx = boardwidth - x - komawidth
        return Coords(ys | mx)

    clssorted = clssort(colist, False)
    r = 0
    for b in range(puzzle.nkoma):
        r = (r << 8) | clssorted[b]
    if not puzzle.ismirrorident:
        return Schash(r)
    rclssorted = clssort(colist, True)
    rr = 0
    for b in range(puzzle.nkoma):
        rr = (rr << 8) | rclssorted[b]
#    print('@hash', hex(r), hex(rr), puzzle.komacls)
    return Schash(min(r, rr))

#------------------------------------------------------------------------
# board matrix functions
#
def makemask(puzzle: Puzzle, kcls: Komacls, co: Coords):
    mask = []
    for mrow in puzzle.clsshape[kcls]:
        mask.append(mrow << cox(co))
    return mask


def collidep(puzzle: Puzzle, kcls: Komacls, co: Coords, bmx: Bmatrix) -> bool:
    if co == Coords(0):
        return False
    ce = co + puzzle.clssiz[kcls]
    mask = makemask(puzzle, kcls, co)
    sum = 0
    for yo in range(coy(puzzle.clssiz[kcls])):
        sum += bmx[coy(co) + yo] & mask[yo]
    if sum != 0:
        return True
    return False


def createbmx(puzzle: Puzzle) -> Bmatrix:
    fulrow = (1 << cox(puzzle.bsize)) - 1
    walrow = (1 << (cox(puzzle.bsize) - 1)) | 1
    bmx = Bmatrix([fulrow] + \
                  [walrow for i in range(coy(puzzle.bsize) - 2)] + \
                  [fulrow])
    for co in puzzle.extwall:
        bmx[coy(co)] |= 1 << cox(co)
    # row (0, last) are the same object but not rewritten
#    for r in bmx:
#        print(bin(r)[-1:1:-1])
    return bmx


def drawerasebmx(puzzle: Puzzle, kcls: Komacls, co: Coords,
                 bmx: Bmatrix, mode: int = 2) -> None:
    '''
    mode: 0: erase, 1: draw, 2: reverse
    '''
#    print(f'(draw){kcls = }, co = {hex(co)}')
#    for r in bmx:
#        print(bin(r)[-1:1:-1])
    mask = makemask(puzzle, kcls, co)
    for yo in range(coy(puzzle.clssiz[kcls])):
        match mode:
            case 0:
                bmx[coy(co) + yo] &= ~mask[yo]
            case 1:
                bmx[coy(co) + yo] |= mask[yo]
            case 2:
                bmx[coy(co) + yo] ^= mask[yo]
#    for r in bmx:
#        print(bin(r)[-1:1:-1])

    return


def makebmatrix(puzzle: Puzzle, col: Colist | list[Coords],
                xkoma: Komaid = Komaid(-1)) \
        -> Bmatrix:
    '''
    makeup bmatrix: for collision detection & drawing
    xkoma is name of excluded koma (set False when draw all koma)
    '''
    bmx = createbmx(puzzle)
    for kid in range(1, puzzle.nkoma + 1):
        if col[kid] != 0 and kid != xkoma:  # maybe 0 if goal
            drawerasebmx(puzzle, puzzle.komacls[kid], col[kid], bmx,
                         mode = 1)

    return bmx

#------------------------------------------------------------------------
# goal functions
#
def isgoal(puzzle: Puzzle, colist: Colist, ph: int) -> bool:
    match puzzle.goaltype:
        case Goaltype.BYCLSHASH:
            # (all komaclass's coords are specified):
            if puzzle.goal_schash == ph:
                return True
            else:
                return False
        case Goaltype.BYID:
            cnt = 0
            for kid, gcoords in puzzle.goal_koma:
#                print(f'@{kid}-{hex(colist[kid])}:{hex(gcoords)}', end = '|')
                if colist[kid] == gcoords:
                    cnt += 1
#            print(cnt)
            if cnt == len(puzzle.goal_koma):
                return True
            else:
                return False
        case Goaltype.BYCLS:
            # (partial komaclass's coords are specified):
            cnt = 0
            for kid, gcoords in puzzle.goal_koma:
                gcls = puzzle.komacls[kid]
                # count if any koma in the class is at the coords.
                for ki in range(1, puzzle.nkoma + 1):
                    if puzzle.komacls[ki] == gcls and \
                       colist[ki] == gcoords:
                        cnt += 1
                        break
            if cnt == len(puzzle.goal_koma):
                return True
            else:
                return False

#------------------------------------------------------------------------
# print functions
#
def printnamematrix(puzzle: Puzzle, colist: Colist,
                    file: TextIO = sys.stdout) -> None:
# to print raw Bmatrix (np.ndarray):
#    print(makebmatrix(puzzle, poset, None))
#    return
# print with koma name:
    by, bx = co2yx(puzzle.bsize)
    bnmx = [['. ' for x in range(bx)] for y in range(by)]
    for i in range(len(puzzle.extwall)):
        y, x = co2yx(puzzle.extwall[i])
        bnmx[y][x] = '  '
    for kid in range(1, puzzle.nkoma + 1):
        if colist[kid] == 0:
            continue;
        ky, kx = co2yx(puzzle.clssiz[puzzle.komacls[kid]])
        cy, cx = co2yx(colist[kid])
        for yy in range(ky):
            px = puzzle.clsshape[puzzle.komacls[kid]][yy]
            for xx in range(kx):
                if px & 1 != 0:
                    bnmx[cy + yy][cx + xx] = puzzle.komanamshort[kid]
                px >>= 1
    for y in range(1, by - 1):
        for x in range(1, bx - 1):
            print(bnmx[y][x], end = ' ', file = file)
        print(file = file)
    return


def printbestans(puzzle: Puzzle, foundans: list[Mcr],
                 initcolist: Colist, isoptrlc: bool) -> None:
    bestrs = None
    for mcr in foundans:
        if isoptrlc:
            if bestrs is None or len(mcr.movehist) < bestrs:
                bestrs = len(mcr.movehist)
                bestmovehist = mcr.movehist
        else:
            if bestrs is None or mcr.rlc < bestrs:
                bestrs = mcr.rlc
                bestmovehist = mcr.movehist
    printhist(puzzle, bestmovehist)
    sys.exit(0)
#NEVERREACHED


def printhist(puzzle: Puzzle, moves: Movehist) -> None:
    bmatrix = makebmatrix(puzzle, Colist(puzzle.initcolist))
    print('initial:')
    printnamematrix(puzzle, Colist(puzzle.initcolist))
    rectlin = 0
    strlin = 0
    lastmkoma: Komaid
    lastmdir: Dirid
    colist = list(puzzle.initcolist)
    for cnt in range(len(moves)):
        mkoma, mdir = moves[cnt]  # (KOMAID, DIRID)
        if cnt != 0:
            if mkoma == lastmkoma:
                if mdir == lastmdir:
                    pass
                else:
                    strlin += 1
            else:
                strlin += 1
                rectlin += 1
            print(f'step {cnt}, rectlin {rectlin}, strlin {strlin}: ' +
                  f'"{puzzle.komanam[mkoma]}" to {dirname[mdir]}:')
            colist[mkoma] = Coords(colist[mkoma] + dirvec[mdir])
            printnamematrix(puzzle, Colist(tuple(colist)))
        lastmkoma, lastmdir = mkoma, mdir
    return


def printpuzzle(puzzle):
    print(f'puzzle: {puzzle.name}')
    print(f'        (y, x) = {co2yx(puzzle.bsize - 0x22)} (including border)')
    print(f'        mirrorident = {puzzle.ismirrorident}')
    print(f'        goaltype = {puzzle.goaltype}', end = '')
    if puzzle.goaltype == Goaltype.BYCLSHASH:
        print(f' (hash = {hex(puzzle.goal_schash)})')
    else:
        print()

    print('koma classes:')
    for kcls in range(1, len(puzzle.clssiz)):
        kcy, kcx = co2yx(puzzle.clssiz[kcls])
        print(f'  (#{kcls:2d}) {puzzle.clsnam[kcls]}: ' + \
              f'{puzzle.clsnam[kcls]} = ' + \
              f'({kcy}, {kcx})')
        print('        koma = {', end = '')
        for i in range(1, puzzle.nkoma + 1):
            if puzzle.komacls[i] == kcls:
                print(puzzle.komanam[i] + ', ', end = '')
        print('}')
        for y in range(kcy):
            kx = puzzle.clsshape[kcls][y]
            print('        ', end = '')
            for x in range(kcx):
                if kx & 1 != 0:
                    print('o ', end = '')
                else:
                    print('. ', end = '')
                kx >>= 1
            print()
            
    print('koma:')
#    for kid in range(1, puzzle.nkoma + 1):
#        print(f'  (#{kid:2d}) {puzzle.komanamshort[kid]}: ' + \
#              f'{puzzle.komanam[kid]} ' + \
#              f'(class "{puzzle.clsnam[puzzle.komacls[kid]]}")')
    print('  init:')
    printnamematrix(puzzle, puzzle.initcolist)
    if puzzle.goaltype == Goaltype.BYID:
        print('\n  goal (koma):')
    else:
        print('\n  goal (komaclass):')
    gkomalist = [0] * (puzzle.nkoma + 1)
    for id, co in puzzle.goal_koma:
        gkomalist[id] = co
    printnamematrix(puzzle, Colist(tuple(gkomalist)))
    print()

    return


def printoptions(opts: Options):
    print('options:')
    print(f'    XML file: {opts.filename}')
    print('    mode: optimal ', end = '')
    if opts.isoptrlc:
        print('RLC search')
    else:
        print('# step search')
    print('    paralell search: ', end = '')
    if opts.isparalell:
        print(f'True (max #procs: {opts.maxnprocs}, ' + \
              f'min #cand: {opts.minnsearchdiv})')
    else:
        print('False')
    if opts.ischeckonly:
        print('    * check only (stop)')
    elif 0 <= opts.stopsteps:
        print('    * stop at step {opts.stopsteps}')
    print()

    return
          

#........................................................................
if __name__ == '__main__':
    puzzle = Puzzle()
    puzzle.bsize = yx2co((7, 6))
    print(puzzle)
# debug co2yx(), yx2co()
## debug co2cov(), cov2co()
    for komawidth in [1, 2]:
        print(f'non-mirror, mirror: (komawidth {komawidth})')
        for y in range(1, coy(puzzle.bsize) - 2 + 1):
            for x in range(1, cox(puzzle.bsize) - 2 - (komawidth - 1) + 1):
#                co = Coords((y, x))
#                cov = co2cov(puzzle, co)
#                cco = cov2co(puzzle, cov)
                yx = (y, x)
                co = yx2co(yx)
                cyx = co2yx(co)
                mco = comirror(co, komawidth, cox(puzzle.bsize))
                mcyx = co2yx(mco)
                print(f'{yx} -> {hex(co)},{hex(mco)} -> {cyx},{mcyx}')

#------------------------------------------------------------------------
# system
def errorstop(message: str) -> NoReturn:
    print(message, file = sys.stderr)
    exit(11)

def warn(message: str):
    print(message, file = sys.stderr)
    return
