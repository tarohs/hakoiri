import xml.etree.ElementTree as et
from typing import Optional
import copy
import re
import sys

import hakocom as hi
from hakocom import Coords, \
    Komaid, Komacls, Colist, Codict, Schash, Sclist, Dirid, \
    Move, Movehist, Rlc, Bmatrix, \
    Goaltype, Mcr, \
    Puzzle, Options
from hakocom import cox, coy, co2yx, yx2co

def costr(s: str) -> Coords:
    try:
        y, x = map(int, s.split(','))
    except ValueError:
        hi.errorstop(f'"{s}" is not coords')
    return yx2co((y, x))

def boolstr(s: Optional[str]) -> bool:
    if s == 'True':
        return True
    elif s == 'False':
        return False
    hi.errorstop(f'"{s}" is not bool (True/False)')

def readxml(opts: Options) -> Puzzle:
    puzzle = Puzzle()
    try:
        root = et.parse(opts.filename).getroot()
    except FileNotFoundError:
        hi.errorstop(f'file not found: {opts.filename}')
    except et.ParseError:
        hi.errorstop(f'file {opts.filename}: could not parse XML file')
    if root.tag != 'puzzle':
        hi.errorstop(f'file {opts.filename}: not a puzzle file?')
    puzzle.name = root.attrib['name']

#........................................................................
# board
#
    if (child := root.find('board')) is None:
        hi.errorstop('need <board> section')
    if (cf := child.find('size')) is None or cf.text is None:
        hi.errorstop('need <board> <size>')
    puzzle.bsize = costr(cf.text)
    extwall = []
    ew = child.findall('extwall')
    if ew is not None:
        for e in ew:
            if e.text is not None:
                extwall.append(costr(e.text))
    puzzle.extwall = extwall
    if (cf := child.find('mirrorident')) is not None:
        puzzle.ismirrorident = boolstr(cf.text)
    else:
        puzzle.ismirrorident = True
    if (cf := child.find('goaltype')) is not None:
        match cf.text:
            case 'byid':
                puzzle.goaltype = Goaltype.BYID
            case 'byclass':
                puzzle.goaltype = Goaltype.BYCLS
            case _:
                hi.errorstop(f'unknown goaltype {cf.text}')

#........................................................................
# koma class to size/shape
#
    child = root.find('clssiz')
    if child is None:
        hi.errorstop('need <clssiz> section')
    namsiz: dict[str, Coords] = {}  # local
    bmpsiz: dict[str, str] = {}  # local
    for cls in child.findall('class'):
        nam = cls.attrib['name']
        if nam in [i[0] for i in namsiz]:
            hi.errorstop(f'duplicated class name "{nam}"')
        if (csiz := cls.find('size')) is not None and csiz.text is not None:
            namsiz[nam] = costr(csiz.text)
        else:
            hi.errorstop(f'size for class {nam} not defined')
        shpstr: list[str] = []
        
        if (cbmp := cls.find('bitmap')) is not None:
            bmpsiz[nam] = str(cbmp.text)
    # (dict order is in place)
    puzzle.clsnam = ['none'] + list(namsiz.keys())
    puzzle.clssiz = [Coords(0)] + [s for i, s in namsiz.items()]
    ol = [Komacls(i) for i in range(len(puzzle.clsnam))]
    namcls:dict[str, Komacls] = dict(zip(puzzle.clsnam, ol)) # local
    clsshape = [[0]]
    for ci in range(1, len(puzzle.clssiz)):
        if puzzle.clsnam[ci] in bmpsiz.keys():
            bmpstr = re.sub(r'[^01]', '', bmpsiz[puzzle.clsnam[ci]])
            ky = puzzle.clssiz[ci] >> 4
            kx = puzzle.clssiz[ci] & 0x0f
            if len(bmpstr) != ky * kx:
                hi.errorstop(
                    f'bitmap {bmpstr} doesnot match to size ({ky}, {kx})')
            cshape = []
            rprod = 1
            ror = 0
            for yy in range(ky):
                rb = bmpstr[kx - 1::-1]
                r = int(rb, 2)
                cshape.append(r)
                bmpstr = bmpstr[kx:]
                rprod *= r
                ror |= r
                if rb != rb[::-1]:
                    puzzle.ismirrorident = False
            if rprod == 0:
                hi.errorstop(
                    f'bitmap of class "{puzzle.clsnam[ci]}" has row of 0')
            if ror != (1 << kx) - 1:
                hi.errorstop(
                    f'bitmap of class "{puzzle.clsnam[ci]}" has column of 0')
        else:
            rowbmp = (1 << cox(puzzle.clssiz[ci])) - 1
            cshape = []
            for row in range(coy(puzzle.clssiz[ci])):
                cshape.append(rowbmp)
            
        clsshape.append(cshape)
    puzzle.clsshape = clsshape
#........................................................................
# koma & goal
#
    child = root.find('komaset')
    if child is None:
        hi.errorstop('no <komaset> section')
    komacls: list[Komacls] = [Komacls(0), ]
    komanam = ['', ]
    knsdict: dict[Komaid, str] = {} # local
    initcol: list[Coords] = [Coords(0), ]
    gkoma: Codict = Codict({}) # local
    kid = Komaid(1)
    for km in child.findall('koma'):
        if (kmn := km.attrib['name']) is not None:
            komanam.append(kmn)
        else:
            hi.errorstop('name for koma not defined')
        if (kms := km.find('short')) is not None:
            ks = (str(kms.text) + '  ')[:2]
            if ks in knsdict.values():
                hi.warn(f'(warning) short name "{ks}" duplicates ' +\
                     f'for koma "{kmn}" (ignored)')
            else:
                knsdict[kid] = ks
        if (kmc := km.find('class')) is not None:
            kc = str(kmc.text)
            if kc in namcls:
                komacls.append(Komacls(namcls[kc]))
            else:
                hi.errorstop(f'komaclass name "{kc}" not defined')
        else:
            hi.errorstop(f'komaclass for koma "{kmn}" not defined')
        if (kmc := km.find('init')) is not None and kmc.text is not None:
            initcol.append(costr(kmc.text))
        else:
            hi.errorstop(f'koma init coords for koma "{kmn}" not defined')
        if (kmg := km.find('goal')) is not None and \
           (kg := kmg.text) is not None:
            gkoma[kid] = costr(kg)
        kid = Komaid(kid + 1)
#------------------------------------------------------------------------
# make struct puzzle, check & display init
    puzzle.nkoma = kid - 1
    puzzle.komanam = komanam
    puzzle.initcolist = Colist(tuple(initcol))
# make goal class & either goal_koma/goal_schash from gkoma
    if len(gkoma) == 0:
        hi.errorstop('no goal')
# if goaltype == byid, and goal koma not unique in its class exists,
#   make new class, copy class size/shape & modify its komacls
    if puzzle.goaltype == Goaltype.BYID:
        ncls = len(puzzle.clsnam)
        nccnt: dict[Komacls, int] = dict()
        for gkid in list(gkoma.keys()):
            gkcls = komacls[gkid]
            if 2 <= len(list(filter(lambda x: x == gkcls, komacls))):
                if gkcls in nccnt:
                    nccnt[gkcls] += 1
                else:
                    nccnt[gkcls] = 2
                puzzle.clsnam.append(puzzle.clsnam[gkcls] + \
                                     '_' + str(nccnt[gkcls]))
                puzzle.clssiz.append(copy.deepcopy(puzzle.clssiz[gkcls]))
                puzzle.clsshape.append(copy.deepcopy(puzzle.clsshape[gkcls]))
                komacls[gkid] = Komacls(ncls)
                ncls += 1
    # gkomalist later used by checkcolist(GOAL)
    gkomalist: list[Coords] = [Coords(0)] * (puzzle.nkoma + 1)
    for kid, kcoords in gkoma.items():
        gkomalist[kid] = kcoords
    puzzle.goal_koma = [(kid, gkoma[kid]) for kid in gkoma.keys()]
# goaltype <- byclshash if classes for all koma are specified
    puzzle.komacls = komacls + [Komacls(0xff)]
#    if puzzle.goaltype == Goaltype.BYCLS and
    if len(gkoma) == puzzle.nkoma:
        puzzle.goal_schash = \
            hi.hashcolist(puzzle, Colist(tuple(gkomalist)))
        puzzle.goaltype = Goaltype.BYCLSHASH
    if puzzle.goaltype == Goaltype.BYCLS:
# if all the goal specified koma are unique in its class,
# changing goaltype to byid is slightly faster
        gidcls = {id: puzzle.komacls[id] for id in gkoma.keys()}
        print('@', gidcls)
        dupcnt = 0
        for gcls in gidcls.values():
            if 2 <= len(list(filter(lambda x: x == gcls, komacls))):
                dupcnt += 1
        print(dupcnt)
        if dupcnt == 0:
            puzzle.goaltype = Goaltype.BYID

# make short name if nothing
    for ki in range(1, puzzle.nkoma + 1):
        kid = Komaid(ki)
        if kid in knsdict.keys():
            continue
        knam = komanam[kid]
        if len(knam) == 1:
            kns = knam + ' '
            if kns in knsdict.values():
                hi.errorstop(
                    f'duplicated 1-letter Koma name "{knam}" with others')
            knsdict[kid] = kns
        else:
            for i in range(1, len(knam)):
                if not knam[0] + knam[i] in knsdict.values():
                    knsdict[kid] = knam[0] + knam[i]
                    break
            else:
                hi.errorstop(f'duplicated auto gen Koma name for "{knam}"')
    puzzle.komanamshort = [''] + \
        [knsdict[Komaid(i)] for i in range(1, puzzle.nkoma + 1)]

# check init & goal
    checkcolist(puzzle, Colist(tuple(initcol)))
    checkcolist(puzzle, Colist(tuple(gkomalist)))

    return puzzle
#------------------------------------------------------------------------


def checkcolist(puzzle, colist: Colist) -> None:
    '''
    stop program if errs
    '''
    lastcol = [Coords(0), ] * (puzzle.nkoma + 1)
    bmx: Bmatrix = hi.makebmatrix(puzzle, lastcol)
    for kid in range(1, puzzle.nkoma + 1):
        kcoords = colist[kid]
        if kcoords == 0:  # None may exist if goal
            continue
        if coy(puzzle.bsize) <= \
               coy(kcoords) + coy(puzzle.clssiz[puzzle.komacls[kid]]) or \
           cox(puzzle.bsize) <= \
               cox(kcoords) + cox(puzzle.clssiz[puzzle.komacls[kid]]):
            hi.errorstop(f'koma {kid} ("{puzzle.komanam[kid]}") at ' +\
                  f'{co2yx(kcoords)} exceeds board size ' +\
                  f'{co2yx(puzzle.bsize)}')
        if 1 < kid and \
           hi.collidep(puzzle, puzzle.komacls[kid], colist[kid], bmx):
            hi.printnamematrix(puzzle, Colist(tuple(lastcol)),
                               file = sys.stderr)
            hi.errorstop(
                f'koma {kid} ("{puzzle.komanam[kid]}") collides at ' +\
                f'{co2yx(colist[kid])}')
        lastcol[kid] = kcoords
        hi.drawerasebmx(puzzle, puzzle.komacls[kid], kcoords, bmx, mode = 1)
        # draw rect koma
    return

#........................................................................
# use 'hakoiri -c' now.
#
#if __name__ == '__main__':
#    puzzle = readxml('hakoiri-basic.xml', True)
#    printpuzzle(puzzle)



