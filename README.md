hakoiri.py - sliding block puzzle solver
====

[Hakoiri Musume (Wikipedia, Japanese)](https://ja.wikipedia.org/wiki/%E7%AE%B1%E5%85%A5%E3%82%8A%E5%A8%98_(%E3%83%91%E3%82%BA%E3%83%AB)) or [Klotski (Wikipedia, English)](https://en.wikipedia.org/wiki/Klotski) is a name of "sliding block" puzzle.

I wrote a Japanese Blog about long journy of this solver;

* Part I: https://zenn.dev/taroh/articles/2703c914dd6597
* Part II: https://zenn.dev/taroh/articles/80874e761c18d7
* Part III: https://zenn.dev/taroh/articles/80874e761c18d7

## The Klotski/Hakoiri-musume class puzzle

This solver can solve a puzzle & find optimal # of "move history" for the Klotski/Hakoiri-musume class puzzles.  The puzzles are defined as follows.

* The game board is (basically) rectangular shaped, with the "wall" around.
* The pieces (Koma) are rectangular (or n-mino like) shaped.
  * Some pieces have the same shape; here I name that "Komaclass" of the pieces.
* Size of the board & all pieces are the multiply of basic unit.  The pieces can move (slide) inside the board by the unit(s) if there is space (gap) to move.
  * Pieces cannot jump over the other pieces, nor go out of the wall.

### Initial state & goal of the game

Initial location of all pieces are given.
The goal of a game is either
1. to move specific (one, two, ..., all) piece(s) to the given goal location,
2. to move specific (one, two, ..., all) Komaclass(es) of piece to the given goal location.

### Example

For example, the most basic Hakoiri-musume (Klotski) (puzzles/hakoiri-basic.xml) is as followings.


```
  init:
ch mu mu ha 
ch mu mu ha 
sf ky ky sb 
sf ka sa sb 
wa .  .  sh 

  goal (koma):
.  .  .  .  
.  .  .  .  
.  .  .  .  
.  mu mu .  
.  mu mu .  
```

(In the original Klotski, each pieces does not have names (you may name as "s1, s2, ..." in the XML definition), while pieces for Hakoiri-musume have identical name of a family - "musume" (daughter), "chichi" (father), "haha" (mother), etc.)

* On the above example, 4x5 (horizontal x vertical) board is given.
* Pieces belongs to 4 Komaclasses:
  * 1x1 sized (Komaclass "small"): "wa" (wasai), "ka" (kadou), "sa" (sadou) & "sh" (shodou),
  * 2x1 sized (Komaclass "horiz"): "ky" (kyoudai),
  * 1x2 sized (Komaclass "vert"): "ch" (chichi), "ha" (haha), "sf" (sofu) & "sb" (sobo),
  * 2x2 sized (Komaclass "big"): "mu" (musume).
* The goal is to move "mu" to the (x, y) = (2, 4) position.
* Only two gaps on the board.  For the step one, only either of
  * "wa" can move to east, or
  * "ka" or "sa" can move to south, or
  * "sh" can move to west.

Please see the definition of example puzzles.

All puzzles I tried are in the puzzles/ directory, and you can check the game general settings, board, piece classes, init & goal state with "python3 hakoiri.py PUZZLENAME.py -c".

## Usage of the solver

```
usage: hakoiri.py [-h] [-p] [-n] [-r] [-t] [-s N] [-x N] [-d N] [-c] [-v]
                  PUZZLENAME
```

* positional arguments: `PUZZLENAME`: specify XML file
* options:
  * `-p, --paralell`: paralell search (default), `-n, --nonparalell`: non paralell search
    * `-x, --maxnprocs N`: maximum # child processes (deault 10, see below)
	* `-d, --minnsearchdiv` N: minimum # candidates in a division for a child (default 200, see below)
  * `-t, --optsteps`: optimize for steps (default), `-r, --optrlc`: optimize for RLC (rectlinear count) (see below)
  * `-s, --stopsteps N`: stop at N steps/RLC
  * `-c, --checkonly`: check koma and print init/goal only and exit
  * `-v, --version`: show program's version number and exit
  * `-h, --help`: show help message and exit

### Counting the number of hands

This solver finds the optimal "steps" or "rectlinear counts."

* a step: a piece move on one basic "unit" then it's one step,
* a rectlinear counts (RLC): one piece can move contiguously (any steps) then it's one RLC.

On the example above, "wa" can move east, then can move east one step more.  Tha's 2 steps, but 1 RLC.

This definition is a big problem when defining the puzzle.  See the chapter "Metrics - a.k.a. redefining the problem" on the document [Sliding Block Puzzles, Part 3 (by NBICKFORD)](https://nbickford.wordpress.com/2012/01/22/sliding-block-puzzles-part-3/).

The solver finds either "optimal step count" or "optimal RLC" solution, and they're different algorhythm.

## about paralell search

By defulat, paralell search is used (using process based fork by concurrent.futures of Python) for large amount of search candidates.

The command line options
  * `-x, --maxnprocs N` specifies max number of children, that should be defined by number of the CPU core.
  * `-d, --minnsearchdiv N`: specifies minimum # of search candidates for one child process.  This should be decided by the fork overhead; when the {time to fork overhead + hand data from parent to child & child to parent (and a bit more - parent must merge the results from children)} exceeds the {time to search `N` candidates}, not to fork child(ren) is faster.

Actual # of fork processes at each step/RLC are decided by the `-x/-d` values dinamically, and displayed on the running monitor as `(p8)` (8 children are forked).

## Puzzle definitions

### The Komaclasses

The Komaclasses (piece classes) are used inside the program to get the optimal hands (move history), however also used for defining puzzle goal.
On the Hakoiri-musume or Klotski, only the "mu" (musume) piece is the aim for the goal, and only the "mu" belongs to the class "big".  In that case, specifying goal by ID of the piece (Komaid) (Goaltype: BYID) is identical to specifying goal by class of the piece (Komacls) (Goaltype: BYCLS/BYCLSHASH).
On the other hand, see the definition of the puzzle "puzzles/chicago-byclass.xml";

```
  init:
ea ea ai ai wo wn 
ea ea au au wo wn 
ch ch yo se .  .  
ce pr ma ma we we 
ce pr in in we we 

  goal (komaclass):
.  .  .  .  .  .  
.  .  .  .  .  .  
.  .  .  .  .  .  
we we .  .  .  .  
we we .  .  .  .  
```

On this puzzle, the goal is when either of "ea" (east) or "we" (west) reaches to the south-west corner of the board.  On the figure above, "we" represent for the komaclass "big" (2x2), but also "ea" belongs to the "big" class, then reaching "ea" at the south-west corner also achieves goal.

The most useful case of defining Komaclass goal is the famous [Conway's "Century and a half" puzzle](https://www.cs.brandeis.edu/~storer/JimPuzzles/ZPAGES/zzzCenturyPuzzles.html) (puzzles/century+.xml).

```
  init:
1  X  X  2  
A  X  X  C  
A  B  .  C  
3  B  .  4  
J  J  K  K  

  goal (komaclass):
K  K  J  J  
4  .  B  3  
C  .  B  A  
C  X  X  A  
2  X  X  1  
```

The goal is to reverse the initial state upside down, however (see the above web page for color),
* the X (red) piece must come to the center-below, because it's unique in the "big" Komaclass,
* either of the K/J (green) piece can come to the left/right-above (i.e. both "K K J J", "J J K K" are allowed as the goal),
* any of the A/B/C (yellow, class "vert") can be any of goal A/B/C position,
* also 1/2/3/4 (blue, class "small") are equivalent.

### How to write XML

You can write original XML file to define a puzzle.
See the examples in the "puzzles/" files.

Note: all the coords here is as (y, x) (vertical-horizontal), starts with (1, 1).  Differs from the explainations above.

* `<puzzle name="NAME">`: main definitions
  * `<board>` section: definition of game board & general config.
    * `<size>`: coords of board size.  The size includes the "wall" block, +2 for the movable spaces for pieces.
	* `<extwall>` (optional): if the game board is not square, use this to set the coords of an extra wall unit.  Can be used repeatedly to set the multiple extra wall units.  See "puzzles/d209.xml" (one extra wall unit at a corner) or "puzzles/simplifcity2.xml" (one "hole" on a wall - put 3 extra wall unit out of a board edge of 4 units).
	* `<goaltype>: (see the above section "The classes")
	  * `byid`: specify coords of the goal target piece(s).
	  * `byclass`: specify coords of the goal target Komaclass(es).
	* `<mirrorident>` (optional): `True` (default) or `False`.  For the efficiancy of the search, "mirrored" state of the board is recorded in the "memoization."  But it should be disabled in some cases (ex. asymmetrical piece exists - automatically be `False`).
  * `<clssiz>` section: definition of size & shape of pieces by Komaclasses.
    * `<class name="CLASSNAME">`:
	  * `<size>`: define the size of the Komaclass (rectangular, or outer bound for non-rectangular pieces)
	  * `<bitmap>` (optional): define shape of the non-rectangular Komaclass by bitmap.  If not exists, the Komaclass pieces is assumed to be rectangular.  `1` stands for existing part of the piece, `0` for a gap.  The `0`/`1` are aligned in order of screen (west to east, north to south), and the number of `0`/`1` must exact be (width x height) defined in the `<size>`.  Only `1` or `0` characters between `<bitmap>...</bitmap>` are valid, so you can write "L" shaped block as any of `1011`, `10/11` or `10<cr>__11`, as you like.
  * `<komaset>` section: definition of each identical piece (Koma)
    * `<koma name="KOMANAME">:
	  * `<class>`: Komaclass of the piece.
	  * `<init>`: initial coords of the piece.  The coords of the north-west (upper-left) corner of the piece (rectangular, or outer bound) represents for the coords for the piece.
	  * `<goal>` (optional): if the piece is (one of) goal-target (or goal-target Komaclass), specify coords (north-west).  If goal-target Komaclass, writing `<goal>` at any of the piece belongs to the Komaclass is equivalent (but write only one `<goal>` on one `<koma>`).
	  * `<short> (optional): define the unique short (2 letter) name of the piece on the board display (`-c` and answer).  If not specified, automatically `KOMANAME` is shorten and used, but if you don't like (or cannot shorten automatically), specify the short name.

### Automatic modification of puzzle definitions/configurations

By checking the definitions of puzzle and command line options, the solver modify some of the definitions/configurations.  The command line option `-c` will help to check the modified definitions/configurations.

* (see above) If any of a piece is asymmetrical, `mirrorident` (search option but belongs to the puzzle definition) turns off (`False`).
* Goaltype and Komaclasses: If you specify goal judgement type by ID of pieces (`byid` option, displayes as `BYID`) or by Komaclass (`byclass` option, displayed as `BYCLS`/`BYCLSHASH`), may be changed.
  * `BYCLS` may be changed to `BYCLSHASH` if all the pieces are specified as the target of goal (as "puzzles/century+50.xml") for the sake of the efficiancy of judgement of the goal.
  * If `BYID` is specified and multiple pieces are in the same Komaclass of a goal target piece, the piece size/shape is copied to a new class and the goal target piece is moved to the new class (otherwise the solution won't be the optimal).


