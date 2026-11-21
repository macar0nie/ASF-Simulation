r"""
ASF simulation model (agent-based, stochastic, discrete time).

Experimental design: 3 transmission pathways x 3 intervention timings = 9 conditions.
  Pathway (only ONE is active in a run):
    direct   - pigs within 1 m of an infectious pen-mate
    indirect - contaminated pens (sick pigs and carcasses), carried between pens by workers
    vector   - hypothetical soft ticks living in each pen; ticks get infected by feeding on
               infectious pigs, stay infected, and infect pigs when they bite
  Intervention timing:
    none  - no outbreak-control action (routine carcass removal still happens)
    early - control measures start on day 3
    late  - the same control measures start on day 15

Each simulated day:
  1. Pigs walk around their pen (6 movement steps per day, one every 4 hours).
     For the direct pathway, close contacts with infectious pigs are counted after each step.
  2. Every susceptible pig gets an infection probability for the day:
         P = 1 - exp(-lambda)                       (equation 1, time step = 1 day)
     where lambda is the hazard of the ACTIVE pathway (equations 2-4). After the intervention
     starts:  lambda_adjusted = lambda x (1 - e)    (equation 5)
  3. Disease states are updated:
         S -> E -> I -> D (dead, carcass in pen) -> R (carcass removed)
                     \-> V (survived, with probability = recovery probability)
  4. Farm actions: intervention measures, carcass removal, moving pigs between pens.
  5. Pen contamination (indirect) and tick infection (vector) are updated; the day is recorded.

This file has no user-interface code. The Streamlit pages and the tests import it.
"""

import math
import random
from dataclasses import asdict, dataclass, field

# ----------------------------------------------------------------------------
# Disease states (letters follow the report's Table I; V = survived/recovered)
# ----------------------------------------------------------------------------
S = "S"  # Susceptible
E = "E"  # Exposed: infected, not yet infectious
I = "I"  # Infectious
V = "V"  # Survived (recovered): assumed not infectious anymore
D = "D"  # Dead: carcass still in the pen
R = "R"  # Removed: carcass taken out of the farm

STATE_NAMES = {S: "Susceptible", E: "Exposed", I: "Infectious", V: "Survived", D: "Dead", R: "Removed"}

ALLOWED_TRANSITIONS = {S: {E}, E: {I}, I: {V, D}, D: {R}, V: set(), R: set()}

PATHWAYS = {"direct": "Direct", "indirect": "Indirect", "vector": "Vector-borne"}
TIMINGS = {"none": "No intervention", "early": "Early intervention", "late": "Late intervention"}
PATHWAY_CODE = {"direct": "D", "indirect": "I", "vector": "V"}
TIMING_CODE = {"none": 1, "early": 2, "late": 3}

INTERVENTION_MEASURES = {
    "direct": "Isolation of detected sick pigs, ban on moving pigs between pens, fewer contact opportunities",
    "indirect": "Cleaning and disinfection, less contamination carried by workers, carcasses removed after 1 day",
    "vector": "Tick control (acaricide treatment of pens and pigs)",
}

# ----------------------------------------------------------------------------
# Fixed model constants (not changed between conditions)
# ----------------------------------------------------------------------------
PEN_WIDTH = 8.0
PEN_DEPTH = 6.0
CORRIDOR = 3.0
MARGIN = 0.4  # pigs keep this distance from the fence
STEPS_PER_DAY = 6  # movement steps per day (every 4 hours)
CONTACT_DISTANCE = 1.0  # metres
SICK_SPEED_FACTOR = 0.5  # infectious pigs move at half speed
CONTAMINATION_DECAY = 0.2  # share of pen contamination that disappears per day
WORKER_CARRYOVER = 0.1  # share of the other pens' average contamination carried in per day
TICK_ACQUISITION = 0.3  # share of uninfected ticks that get infected per day when all pigs in the pen are infectious
ROUTINE_CARCASS_DELAY = 3  # days: normal farm practice, used in every condition
INTERVENTION_CARCASS_DELAY = 1  # days: faster removal (indirect-pathway intervention)


@dataclass
class Settings:
    """All inputs of one simulation run."""

    pathway: str = "direct"  # direct / indirect / vector
    timing: str = "none"  # none / early / late
    early_day: int = 3
    late_day: int = 15
    effectiveness: float = 0.8  # e in equation (5)

    num_pigs: int = 120
    num_pens: int = 6
    initial_infectious: int = 2
    days: int = 60
    seed: int = 42

    direct_coefficient: float = 0.1  # hazard per close contact with an infectious pig
    indirect_coefficient: float = 0.002  # hazard per unit of pen contamination per day
    vector_coefficient: float = 0.6  # hazard per day when ALL ticks in the pen are infected

    recovery_prob: float = 0.05  # chance an infectious pig survives instead of dying
    movement_speed: float = 1.0  # metres per hour inside the pen
    transfers_per_week: float = 6.0  # pigs moved by workers between pens
    detection_delay: int = 2  # days an infectious pig goes unnoticed (direct-pathway isolation)

    latent_days: tuple = (3, 6)
    infectious_days: tuple = (5, 9)

    @property
    def intervention_day(self):
        """Day the intervention starts, or None for no intervention."""
        return {"none": None, "early": self.early_day, "late": self.late_day}[self.timing]

    @property
    def condition(self):
        """Condition code from the report's Table IV, e.g. D1, I2, V3."""
        return f"{PATHWAY_CODE[self.pathway]}{TIMING_CODE[self.timing]}"


@dataclass
class Pig:
    id: int
    pen: int
    x: float
    z: float
    tx: float
    tz: float
    state: str = S
    day_infected: int = -1
    day_infectious: int = -1
    day_dead: int = -1
    latent_len: int = 0
    infectious_len: int = 0
    isolated: bool = False
    route: str = ""


@dataclass
class Result:
    settings: dict
    pens: list
    isolation_pen: dict
    daily: list
    frames: list  # frames[day][step] = [x0, z0, x1, z1, ...]
    states: list  # states[day] = one letter per pig (lower case = in isolation)
    pen_levels: list  # pen_levels[day][pen] = 0..1 exposure level shown on the pen floor
    summary: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def pen_rectangles(num_pens):
    cols = math.ceil(num_pens / 2)
    total_width = cols * PEN_WIDTH
    pens = []
    for p in range(num_pens):
        row = 0 if p < cols else 1
        col = p if row == 0 else p - cols
        min_x = -total_width / 2 + col * PEN_WIDTH
        if row == 0:
            min_z, max_z = -CORRIDOR / 2 - PEN_DEPTH, -CORRIDOR / 2
        else:
            min_z, max_z = CORRIDOR / 2, CORRIDOR / 2 + PEN_DEPTH
        pens.append({"min_x": min_x, "max_x": min_x + PEN_WIDTH, "min_z": min_z, "max_z": max_z, "label": f"Pen {p + 1}"})
    iso_x = total_width / 2 + 3.0
    isolation = {"min_x": iso_x, "max_x": iso_x + 6.0, "min_z": -3.0, "max_z": 3.0, "label": "Isolation"}
    return pens, isolation


def random_point(rect, rng):
    return (
        rng.uniform(rect["min_x"] + MARGIN, rect["max_x"] - MARGIN),
        rng.uniform(rect["min_z"] + MARGIN, rect["max_z"] - MARGIN),
    )


def infection_probability(hazard):
    """Equation (1): P = 1 - exp(-hazard x 1 day). Always between 0 and 1."""
    if hazard is None or math.isnan(hazard) or hazard <= 0:
        return 0.0
    return 1.0 - math.exp(-hazard)


# ----------------------------------------------------------------------------
# The simulation
# ----------------------------------------------------------------------------
class Simulation:
    def __init__(self, settings: Settings):
        if settings.pathway not in PATHWAYS or settings.timing not in TIMINGS:
            raise ValueError("unknown pathway or timing")
        self.s = settings
        self.rng = random.Random(settings.seed)
        self.day = 0
        self.pens, self.isolation_pen = pen_rectangles(settings.num_pens)
        self.contamination = [0.0] * settings.num_pens  # indirect pathway
        self.tick_infection = [0.0] * settings.num_pens  # vector pathway: share of infected ticks per pen

        # Pigs: pig i goes to pen (i mod number of pens).
        self.pigs = []
        for i in range(settings.num_pigs):
            pen = i % settings.num_pens
            x, z = random_point(self.pens[pen], self.rng)
            tx, tz = random_point(self.pens[pen], self.rng)
            self.pigs.append(Pig(i, pen, x, z, tx, tz))

        # Introduce ASF: the first pigs of Pen 1 start as INFECTIOUS on day 0.
        for pig in [p for p in self.pigs if p.pen == 0][: settings.initial_infectious]:
            pig.state = I
            pig.day_infected = 0
            pig.day_infectious = 0
            pig.infectious_len = self.rng.randint(*settings.infectious_days)
            pig.route = "initial"

        self.daily, self.pen_levels = [], []
        self.frames = [[self.positions()]]
        self.states = [self.state_string()]
        self.record(new_infections=0, intervention_active=False)

    # ---- intervention ----------------------------------------------------------
    def intervention_active(self):
        start = self.s.intervention_day
        return start is not None and self.day >= start

    def reduction(self):
        """Factor (1 - e) of equation (5) while the intervention is active, else 1."""
        return 1 - self.s.effectiveness if self.intervention_active() else 1.0

    def carcass_delay(self):
        if self.s.pathway == "indirect" and self.intervention_active():
            return INTERVENTION_CARCASS_DELAY
        return ROUTINE_CARCASS_DELAY

    # ---- state changes ---------------------------------------------------------
    def infect(self, pig, route):
        """S -> E. The pig's latent and infectious period lengths are drawn now."""
        pig.state = E
        pig.day_infected = self.day
        pig.route = route
        pig.latent_len = self.rng.randint(*self.s.latent_days)
        pig.infectious_len = self.rng.randint(*self.s.infectious_days)

    def progress(self, pig):
        """Time-driven changes: E -> I, I -> V or D, D -> R."""
        if pig.state == E and self.day - pig.day_infected >= pig.latent_len:
            pig.state = I
            pig.day_infectious = self.day
        elif pig.state == I and self.day - pig.day_infectious >= pig.infectious_len:
            if self.rng.random() < self.s.recovery_prob:
                pig.state = V
            else:
                pig.state = D
                pig.day_dead = self.day
        elif pig.state == D and self.day - pig.day_dead >= self.carcass_delay():
            pig.state = R

    # ---- movement ---------------------------------------------------------------
    def area_of(self, pig):
        return self.isolation_pen if pig.isolated else self.pens[pig.pen]

    def move_pigs(self):
        hours = 24 / STEPS_PER_DAY
        for pig in self.pigs:
            if pig.state in (D, R):
                continue
            speed = self.s.movement_speed * (SICK_SPEED_FACTOR if pig.state == I else 1.0)
            distance = speed * hours
            dx, dz = pig.tx - pig.x, pig.tz - pig.z
            gap = math.hypot(dx, dz)
            if gap <= distance:
                pig.x, pig.z = pig.tx, pig.tz
                pig.tx, pig.tz = random_point(self.area_of(pig), self.rng)
            else:
                pig.x += dx / gap * distance
                pig.z += dz / gap * distance
            area = self.area_of(pig)  # never leave the pen
            pig.x = min(max(pig.x, area["min_x"] + MARGIN), area["max_x"] - MARGIN)
            pig.z = min(max(pig.z, area["min_z"] + MARGIN), area["max_z"] - MARGIN)

    def count_contacts(self, contacts):
        """+1 contact for a susceptible pig for every infectious pen-mate within 1 m."""
        for pen in range(self.s.num_pens):
            sick = [p for p in self.pigs if p.pen == pen and p.state == I and not p.isolated]
            if not sick:
                continue
            for pig in self.pigs:
                if pig.pen != pen or pig.state != S or pig.isolated:
                    continue
                for other in sick:
                    if math.hypot(pig.x - other.x, pig.z - other.z) <= CONTACT_DISTANCE:
                        contacts[pig.id] = contacts.get(pig.id, 0) + 1

    # ---- hazards (equations 2-5) ---------------------------------------------
    def hazard(self, pig, contacts):
        s = self.s
        if s.pathway == "direct":
            lam = s.direct_coefficient * contacts.get(pig.id, 0)
        elif s.pathway == "indirect":
            lam = s.indirect_coefficient * self.contamination[pig.pen]
        else:
            lam = s.vector_coefficient * self.tick_infection[pig.pen]
        return lam * self.reduction()

    # ---- one simulated day -----------------------------------------------------
    def step(self):
        self.day += 1
        s = self.s

        # 1. Movement (+ contacts for the direct pathway)
        contacts = {}
        day_frames = []
        for _ in range(STEPS_PER_DAY):
            self.move_pigs()
            if s.pathway == "direct":
                self.count_contacts(contacts)
            day_frames.append(self.positions())

        # 2. Infection probabilities from the start-of-day situation, applied afterwards
        new_cases = []
        for pig in self.pigs:
            if pig.state != S:
                continue
            if self.rng.random() < infection_probability(self.hazard(pig, contacts)):
                new_cases.append(pig)

        # 3. Disease progression, then the new infections
        for pig in self.pigs:
            self.progress(pig)
        for pig in new_cases:
            self.infect(pig, s.pathway)

        # 4. Farm actions
        if s.pathway == "direct" and self.intervention_active():
            for pig in self.pigs:  # isolate sick pigs once they are noticed
                if pig.state == I and not pig.isolated and self.day - pig.day_infectious >= s.detection_delay:
                    pig.isolated = True
                    pig.x, pig.z = random_point(self.isolation_pen, self.rng)
                    pig.tx, pig.tz = random_point(self.isolation_pen, self.rng)
        transfers_banned = s.pathway == "direct" and self.intervention_active()
        if not transfers_banned:
            self.transfer_pigs()

        # 5. Environment
        self.update_contamination()
        self.update_ticks()

        # 6. Record
        day_frames[-1] = self.positions()
        self.frames.append(day_frames)
        self.states.append(self.state_string())
        self.record(len(new_cases), self.intervention_active())

    def transfer_pigs(self):
        """Workers move healthy-looking pigs between pens (about transfers_per_week per week)."""
        if self.s.num_pens < 2 or self.s.transfers_per_week <= 0:
            return
        expected = self.s.transfers_per_week / 7
        count = int(expected) + (1 if self.rng.random() < expected - int(expected) else 0)
        for _ in range(count):
            movable = [p for p in self.pigs if p.state in (S, E, I, V) and not p.isolated]
            if not movable:
                return
            pig = self.rng.choice(movable)
            pig.pen = self.rng.choice([q for q in range(self.s.num_pens) if q != pig.pen])
            pig.x, pig.z = random_point(self.pens[pig.pen], self.rng)
            pig.tx, pig.tz = random_point(self.pens[pig.pen], self.rng)

    def update_contamination(self):
        """Indirect pathway: sick pigs and carcasses contaminate their pen; contamination fades
        by 20% per day; workers carry 10% of the other pens' average contamination into each pen."""
        if self.s.pathway != "indirect":
            return
        sources = [0] * self.s.num_pens
        for pig in self.pigs:
            if pig.state in (I, D) and not pig.isolated:
                sources[pig.pen] += 1
        old = self.contamination[:]
        n = self.s.num_pens
        for pen in range(n):
            others = (sum(old) - old[pen]) / (n - 1) if n > 1 else 0.0
            carried = WORKER_CARRYOVER * others * self.reduction()
            self.contamination[pen] = old[pen] * (1 - CONTAMINATION_DECAY) + sources[pen] + carried

    def update_ticks(self):
        """Vector pathway: ticks feeding on infectious pigs become infected and stay infected.
        New share infected per day = TICK_ACQUISITION x (share of pigs in the pen that are infectious)
        x (share of ticks not yet infected)."""
        if self.s.pathway != "vector":
            return
        for pen in range(self.s.num_pens):
            alive = [p for p in self.pigs if p.pen == pen and p.state in (S, E, I, V) and not p.isolated]
            if not alive:
                continue
            sick_share = sum(1 for p in alive if p.state == I) / len(alive)
            f = self.tick_infection[pen]
            self.tick_infection[pen] = f + TICK_ACQUISITION * sick_share * (1 - f)

    # ---- recording -------------------------------------------------------------
    def positions(self):
        out = []
        for p in self.pigs:
            out.extend((round(p.x, 2), round(p.z, 2)))
        return out

    def state_string(self):
        return "".join(p.state.lower() if p.isolated else p.state for p in self.pigs)

    def record(self, new_infections, intervention_active):
        counts = {st: 0 for st in (S, E, I, V, D, R)}
        for p in self.pigs:
            counts[p.state] += 1
        self.daily.append(
            {
                "day": self.day,
                **counts,
                "isolated": sum(1 for p in self.pigs if p.isolated and p.state in (E, I, V)),
                "new_infections": new_infections,
                "total_infected": sum(1 for p in self.pigs if p.day_infected >= 0),
                "total_dead": counts[D] + counts[R],
                "intervention_active": intervention_active,
            }
        )
        # Level shown on the pen floors in 3D (0 = clean, 1 = very high exposure)
        if self.s.pathway == "indirect":
            levels = [min(1.0, c * self.reduction() / 30) for c in self.contamination]
        elif self.s.pathway == "vector":
            levels = list(self.tick_infection)
        else:
            levels = [0.0] * self.s.num_pens
        self.pen_levels.append([round(v, 3) for v in levels])

    def summary(self):
        """Performance indicators (report Table V)."""
        n = self.s.num_pigs
        total_infected = sum(1 for p in self.pigs if p.day_infected >= 0)
        peak = max(self.daily, key=lambda d: d[I])
        active_days = [d["day"] for d in self.daily if d[E] + d[I] > 0]
        return {
            "total_infected": total_infected,
            "percent_infected": 100 * total_infected / n,
            "total_deaths": self.daily[-1]["total_dead"],
            "total_survived": self.daily[-1][V],
            "peak_infectious": peak[I],
            "peak_day": peak["day"],
            "outbreak_duration": (max(active_days) if active_days else 0),
            "final_susceptible": self.daily[-1][S],
        }

    def run(self):
        while self.day < self.s.days:
            self.step()
        settings = asdict(self.s)
        settings["condition"] = self.s.condition
        settings["intervention_day"] = self.s.intervention_day
        return Result(settings, self.pens, self.isolation_pen, self.daily, self.frames, self.states, self.pen_levels, self.summary())


def run_simulation(settings: Settings) -> Result:
    return Simulation(settings).run()
