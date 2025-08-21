import xml.etree.ElementTree as et
from typing import Optional
import copy
import re
import sys

import hakocom as hi
from hakocom import Coords, Komaid, Komacls, \
    Colist, Schash, Dirid, \
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

#------------------------------------------------------------------------
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
# koma name to size/shape
#
    child = root.find('clssiz')
    if child is None:
        hi.errorstop('need <clssiz> section')
    cnamsiz: dict[str, Coords] = {}
    cnambmp: dict[str, str] = {}
    cnamset: set[str] = set()
    for cls in child.findall('class'):
        nam = cls.attrib['name']
        if nam in cnamset:
            hi.errorstop(f'duplicated class name "{nam}"')
        cnamset.add(nam)
        if (csiz := cls.find('size')) is not None and csiz.text is not None:
            cnamsiz[nam] = costr(csiz.text)
        else:
            hi.errorstop(f'size for class {nam} not defined')
        if (cbmp := cls.find('bitmap')) is not None:
            cnambmp[nam] = str(cbmp.text)
# convert bitmap to shape
    cnamshape: dict[str, list[int]] = {}
    for cnam in cnamset:
        if cnam in cnambmp:
            bmpstr = re.sub(r'[^01]', '', cnambmp[cnam])
            ky = cnamsiz[cnam] >> 4
            kx = cnamsiz[cnam] & 0x0f
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
                    f'bitmap of class "{cnam}" has row of 0')
            if ror != (1 << kx) - 1:
                hi.errorstop(
                    f'bitmap of class "{cnam}" has column of 0')
        else:
            rowbmp = (1 << cox(cnamsiz[cnam])) - 1
            cshape = []
            for row in range(coy(cnamsiz[cnam])):
                cshape.append(rowbmp)
        cnamshape[cnam] = cshape
#........................................................................
# koma & goal
#
    child = root.find('komaset')
    if child is None:
        hi.errorstop('no <komaset> section')
    knamset: set[str] = set()
    knamcls: dict[str, str] = {}
    knamshort: dict[str, str] = {}
    knaminitcol: dict[str, Coords] = {}
    knamgkoma: dict[str, Coords] = {}
    for km in child.findall('koma'):
        if (knam := km.attrib['name']) is not None:
            knamset.add(knam)
        else:
            hi.errorstop('name for koma not defined')
        if (kms := km.find('short')) is not None:
            ks = (str(kms.text) + '  ')[:2]
            if ks in knamshort.values():
                hi.warn(f'(warning) short name "{ks}" duplicates ' +\
                     f'for koma "{knam}" (ignored)')
            else:
                knamshort[knam] = ks
        if (kmc := km.find('class')) is not None and kmc.text is not None:
            if not kmc.text in cnamset:
                hi.errorstop(f'komaclass name "{kmc.text}" not defined')
            knamcls[knam] = kmc.text
        else:
            hi.errorstop(f'komaclass for koma "{knam}" not defined')
        if (kmc := km.find('init')) is not None and kmc.text is not None:
            knaminitcol[knam] = costr(kmc.text)
        else:
            hi.errorstop(f'koma init coords for koma "{knam}" not defined')
        if (kmg := km.find('goal')) is not None and \
           (kg := kmg.text) is not None:
            knamgkoma[knam] = costr(kg)

#........................................................................
# make struct puzzle, check & display init
#
    for knam in knamset:
# make short name if nothing
        if knam in knamshort.keys():
            continue
# auto make short name
        if len(knam) == 1:
            kns = knam + ' '
            if kns in knamshort.values():
                hi.errorstop(
                    f'duplicated 1-letter Koma name "{knam}" with others')
            knamshort[knam] = kns
        else:
            for i in range(1, len(knam)):
                if not knam[0] + knam[i] in knamshort.values():
                    knamshort[knam] = knam[0] + knam[i]
                    break
            else:
                hi.errorstop(f'duplicated auto gen Koma name for "{nam}"')
# optimize & assign komaclass id
#  number of koma in a class
    ncls = len(cnamset)
    cnamnk = {n: 0 for n in cnamset}
    for knam in knamset:
        cnamnk[knamcls[knam]] += 1

# if goaltype == byid, and goal koma not unique in its class exists,
#   make new class, copy class size/shape & modify its komacls
    if puzzle.goaltype == Goaltype.BYID:
        nccnt: dict[str, int] = {}  # "_2", "_3", ... after class name
        for gknam in list(knamgkoma.keys()):
            if 2 <= cnamnk[knamcls[gknam]]:
                if knamcls[gknam] in nccnt:
                    nccnt[knamcls[gknam]] += 1
                else:
                    nccnt[knamcls[gknam]] = 2
                newcnam = knamcls[gknam] + '_' + str(nccnt[knamcls[gknam]])
                cnamset.add(newcnam)
                cnamsiz[newcnam] = copy.deepcopy(cnamsiz[knamcls[gknam]])
                cnamshape[newcnam] = copy.deepcopy(cnamshape[knamcls[gknam]])
                cnamnk[knamcls[gknam]] -= 1
                knamcls[gknam] = newcnam
                cnamnk[knamcls[gknam]] = 1
                ncls += 1
                
# (continue) assign comaclass
#  area of koma in the class           
    cnamar = {n: 0 for n in cnamset}
    for cnam in cnamset:
        cnamar[cnam] = (cnamsiz[cnam] >> 4) * (cnamsiz[cnam] & 0xf)
    cnan = [(nam, cnamar[nam], cnamnk[nam]) for nam in cnamset]
    # sort order by #koma in the class, then area of koma of the class
    scnan = sorted(sorted(cnan, key = lambda x: x[1]),
                   key = lambda x: x[2], reverse = True)
    puzzle.clsnam = [''] + [scnan[i][0] for i in range(ncls)]
    puzzle.clssiz = [Coords(0)] + \
        [cnamsiz[puzzle.clsnam[i]] for i in range(1, ncls + 1)]
    puzzle.clsshape = [[]] + \
        [cnamshape[puzzle.clsnam[i]] for i in range(1, ncls + 1)]
    # reverse lookup
    cnamcls = {}
    for c in range(1, ncls + 1):
        cnamcls[puzzle.clsnam[c]] = c
    s = 0
#    imin: list[Komacls] = [0, ]
#    imax: list[Komacls] = [0, ]
#    for c in range(1, ncls + 1):
#        nc = cnamnk[puzzle.clsnam[c]]
#        if nc == 1:
#            break
#        imin.append(Komacls(s))
#        imax.append(Komacls(s + nc - 1))
#        s += nc
#    puzzle.clsimin = imin
#    puzzle.clsimax = imax

# optimize & assign koma id
    puzzle.nkoma = len(knamset)
    knamclsid = {knam: cnamcls[knamcls[knam]] for knam in knamset}
    kncc = [(knam, knaminitcol[knam], knamclsid[knam]) for knam in knamset]
    # sort order by komacls, then init coords
    skncc = sorted(sorted(kncc, key = lambda x: x[1]),
                   key = lambda x: x[2])
    puzzle.komanam = [''] + [skncc[i][0] for i in range(puzzle.nkoma)]
    initcolist = [Coords(0)] + [Coords(skncc[i][1])
                                for i in range(puzzle.nkoma)]
    puzzle.initcolist = tuple(initcolist)
    puzzle.komacls = [Komacls(0)] + \
        [Komacls(skncc[i][2]) for i in range(puzzle.nkoma)] + [Komacls(0xff)]
    puzzle.komanamshort = [''] + [knamshort[puzzle.komanam[i]]
                                    for i in range(1, puzzle.nkoma + 1)]
    # reverse lookup
    knamid = {}
    for i in range(1, puzzle.nkoma + 1):
        knamid[puzzle.komanam[i]] = i

    # find final "non-unique in the class" koma
    for fn in range(puzzle.nkoma, 0, -1):
        if 1 < cnamnk[puzzle.clsnam[puzzle.komacls[fn]]]:
            break
##    puzzle.cillen = fn
#    # init cilist[0..cillen - 1] <= [0, 1, ..., cillen - 1]
#    puzzle.initcilist = tuple([Hashidx(i) for i in range(fn)])
    inithash = 0
    for i in range(puzzle.nkoma, 0, -1):
        inithash = (inithash << 8) | initcolist[i]
    puzzle.inithash = Schash(inithash)

# make goal class & either goalkoma/goalhash from gkoma
    if len(knamgkoma) == 0:
        hi.errorstop('no goal')
    # gkomalist later used by checkcolist(GOAL)
    gkomalist: list[Coords] = [Coords(0)] * (puzzle.nkoma + 1)
    for knam, kcoords in knamgkoma.items():
        kid = knamid[knam]
        gkomalist[kid] = kcoords
        puzzle.goalkoma.append((Komaid(kid), kcoords))
#    if puzzle.goaltype == Goaltype.BYCLS and
    if len(puzzle.goalkoma) == puzzle.nkoma:
#        goalhash = 0
#        for id in range(1, puzzle.nkoma + 1):
#            goalhash = (goalhash << 8) | gkomalist[id]
#        puzzle.goalhash = Schash(goalhash)
        puzzle.goalhash = hi.hashcolist(puzzle, gkomalist)
        puzzle.goaltype = Goaltype.BYCLSHASH
    if puzzle.goaltype == Goaltype.BYCLS:
# if all the goal specified koma are unique in its class,
# changing goaltype to byid is slightly faster
        for c, _ in puzzle.goalkoma:
            if 2 <= cnamnk[puzzle.clsnam[puzzle.komacls[c]]]:
                break
        else:
            puzzle.goaltype = Goaltype.BYID

#    print('@@', puzzle)
#    print(hex(puzzle.inithash))

# check init & goal
    checkcolist(puzzle, Colist(initcolist))
    checkcolist(puzzle, Colist(gkomalist))

    return puzzle

#------------------------------------------------------------------------
def checkcolist(puzzle, colist: Colist) -> None:
    '''
    stop program if errs
    '''
    lastcol: Colist = Colist([Coords(0), ] * (puzzle.nkoma + 1))
    bmx: Bmatrix = hi.createbmx(puzzle)
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
           hi.collidep(colist[kid], puzzle.clssiz[puzzle.komacls[kid]],
                       puzzle.clsshape[puzzle.komacls[kid]], bmx):
            hi.printnamematrix(puzzle, lastcol,
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



