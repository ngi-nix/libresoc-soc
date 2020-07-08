// WIP pipeline loop demo

let instruction_queue: (null | Instruction)[] = [];
let instruction_cancel_queue: (null | Instruction[])[] = [];

class Instruction {
    pc: number;
    reservation_station: null | ReservationStation;
    canceled: boolean;
    constructor(pc: number) {
        this.pc = pc;
        this.reservation_station = null;
        this.canceled = false;
    }
    toString() {
        return `0x${this.pc.toString(16)}`
    }
}

class StageConnectionPoint {
    stage: Stage;
    x: number;
    y: number;
    constructor(stage: Stage, x: number, y: number) {
        this.stage = stage;
        this.x = x;
        this.y = y;
    }
}

const enum State {
    Empty,
    Starting,
    Executing,
    Canceling,
    Finished,
    Stalled,
}

function assert_unreachable(v: never): never { return v; }

let diagram: HTMLElement;
class Stage {
    static readonly GRID_CELL_WIDTH = 100;
    static readonly GRID_CELL_HEIGHT = 50;
    static readonly BOX_WIDTH = 90;
    static readonly BOX_HEIGHT = 40;
    static readonly ALL_STAGES: Stage[] = [];
    x: number;
    y: number;
    name: string;
    instruction: Instruction | null;
    group_node: SVGGElement;
    box_node: SVGRectElement;
    name_node: SVGTextElement;
    status_text_node: SVGTextElement;
    instruction_text_node: SVGTextElement;
    top_connection_point: StageConnectionPoint;
    bottom_connection_point: StageConnectionPoint;
    left_connection_point: StageConnectionPoint;
    right_connection_point: StageConnectionPoint;
    state: State = State.Empty;
    constructor(x: number, y: number, name: string) {
        Stage.ALL_STAGES.push(this);
        this.x = x;
        this.y = y;
        this.name = name;
        this.instruction = null;
        this.group_node = document.createElementNS("http://www.w3.org/2000/svg", "g");
        this.box_node = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        this.box_node.setAttribute("width", String(Stage.BOX_WIDTH));
        this.box_node.setAttribute("height", String(Stage.BOX_HEIGHT));
        this.box_node.setAttribute("fill", "white");
        this.box_node.setAttribute("stroke", "black");
        this.box_node.setAttribute("x", String(x));
        this.box_node.setAttribute("y", String(y));
        this.group_node.appendChild(this.box_node);
        this.name_node = document.createElementNS("http://www.w3.org/2000/svg", "text");
        this.name_node.setAttribute("x", String(x + 5));
        this.name_node.setAttribute("y", String(y + 5));
        this.name_node.setAttribute("class", "stage_title");
        this.name_node.textContent = name;
        this.group_node.appendChild(this.name_node);
        this.status_text_node = document.createElementNS("http://www.w3.org/2000/svg", "text");
        this.status_text_node.setAttribute("x", String(x + 5));
        this.status_text_node.setAttribute("y", String(y + Stage.BOX_HEIGHT - 5));
        this.status_text_node.setAttribute("class", "stage_status_text");
        this.status_text_node.textContent = "";
        this.group_node.appendChild(this.status_text_node);
        this.instruction_text_node = document.createElementNS("http://www.w3.org/2000/svg", "text");
        this.instruction_text_node.setAttribute("x", String(x + Stage.BOX_WIDTH - 5));
        this.instruction_text_node.setAttribute("y", String(y + 5));
        this.instruction_text_node.setAttribute("class", "stage_instruction_text");
        this.instruction_text_node.textContent = "";
        this.group_node.appendChild(this.instruction_text_node);
        diagram.appendChild(this.group_node);
        this.top_connection_point = new StageConnectionPoint(this, x + Stage.BOX_WIDTH / 2, y);
        this.bottom_connection_point = new StageConnectionPoint(this, x + Stage.BOX_WIDTH / 2, y + Stage.BOX_HEIGHT);
        this.left_connection_point = new StageConnectionPoint(this, x, y + Stage.BOX_HEIGHT / 2);
        this.right_connection_point = new StageConnectionPoint(this, x + Stage.BOX_WIDTH, y + Stage.BOX_HEIGHT / 2);
        this.state = State.Empty;
    }
    update_visible_state() {
        let bk_color;
        let status_text;
        switch (this.state) {
            case State.Empty:
                status_text = "empty"; bk_color = "#FFFFFF";
                break;
            case State.Starting:
                status_text = "starting"; bk_color = "#C0C000";
                break;
            case State.Executing:
                status_text = "executing"; bk_color = "#80FF80";
                break;
            case State.Canceling:
                status_text = "canceling"; bk_color = "#C04040";
                break;
            case State.Finished:
                status_text = "finished"; bk_color = "#8080FF";
                break;
            case State.Stalled:
                status_text = "stalled"; bk_color = "#909090";
                break;
            default:
                return assert_unreachable(this.state);
        }
        this.box_node.setAttribute("fill", bk_color);
        this.status_text_node.textContent = status_text;
        this.instruction_text_node.textContent = String(this.instruction || "");
    }
    tick_setup() { }
    tick() { }
}

class ReservationStation extends Stage {
    next_state: State;
    constructor(x: number, y: number, name: string) {
        super(x, y, name);
        this.state = State.Empty;
        this.next_state = State.Empty;
    }
    tick_setup() {
        this.next_state = this.state;
        switch (this.state) {
            case State.Empty:
                break;
            case State.Starting:
                if (this.instruction!.canceled) {
                    this.next_state = State.Canceling;
                }
                else if (setup_stage.instruction === this.instruction) {
                    this.next_state = State.Executing;
                }
                break;
            case State.Executing:
                if (this.instruction!.canceled) {
                    this.next_state = State.Canceling;
                }
                else if (finish_stage.instruction === this.instruction) {
                    this.next_state = State.Finished;
                }
                break;
            case State.Canceling:
                this.next_state = State.Empty;
                break;
            case State.Finished:
                this.next_state = State.Empty;
                break;
            default:
                throw new TypeError("invalid state value");
        }
    }
    tick() {
        switch (this.state) {
            case State.Empty:
                if (instruction_queue[0]) {
                    instruction_queue[0].reservation_station = this;
                    this.instruction = instruction_queue[0];
                    instruction_queue[0] = null;
                    this.state = State.Starting;
                }
                break;
            case State.Starting:
            case State.Executing:
                this.state = this.next_state;
                break;
            case State.Canceling:
                this.instruction!.reservation_station = null;
                this.instruction = null;
                this.state = State.Empty;
                break;
            case State.Finished:
                this.instruction!.reservation_station = null;
                this.instruction = null;
                this.state = State.Empty;
                break;
            default:
                throw new TypeError("invalid state value");
        }
    }
}

class LoopHeaderStage extends Stage {
    next_state: State;
    next_instruction: Instruction | null;
    constructor(x: number, y: number) {
        super(x, y, "loop hdr");
        this.state = State.Empty;
        this.next_state = State.Empty;
        this.next_instruction = null;
    }
}

class LoopFooterStage extends Stage {
    next_state: State;
    next_instruction: Instruction | null;
    constructor(x: number, y: number) {
        super(x, y, "loop ftr");
        this.state = State.Empty;
        this.next_state = State.Empty;
        this.next_instruction = null;
    }
}

class ComputeStage extends Stage {
    next_state: State;
    next_instruction: Instruction | null;
    constructor(x: number, y: number, name: string) {
        super(x, y, name);
        this.state = State.Empty;
        this.next_state = State.Empty;
        this.next_instruction = null;
    }
}

class FinishStage extends Stage {
    next_state: State;
    next_instruction: Instruction | null;
    constructor(x: number, y: number) {
        super(x, y, "finish");
        this.state = State.Empty;
        this.next_state = State.Empty;
        this.next_instruction = null;
    }
}

class SetupStage extends Stage {
    next_state: State;
    next_instruction: Instruction | null;
    stalled: boolean;
    constructor(x: number, y: number) {
        super(x, y, "setup");
        this.state = State.Empty;
        this.next_state = State.Empty;
        this.next_instruction = null;
        this.stalled = false;
    }
    tick_setup() {
        this.next_state = this.state;
        this.next_instruction = this.instruction;
        switch (this.state) {
            case State.Empty:
                for (let rs of reservation_stations) {
                    if (rs.state == State.Starting) {
                        this.next_instruction = rs.instruction;
                        this.next_state = State.Executing;
                        break;
                    }
                }
                break;
            case State.Executing:
                break;
            case State.Canceling:
                this.next_state = State.Empty;
                this.next_instruction = null;
                break;
            default:
                throw new TypeError("invalid state value");
        }
    }
    tick() {
        switch (this.state) {
            case State.Empty:
                for (let rs of reservation_stations) {

                }
                break;
            case State.Stalled:
                break;
            case State.Executing:
                break;
            case State.Canceling:
                break;
            default:
                throw new TypeError("invalid state value");
        }
    }
}

class Connection {
    src_connection_point: StageConnectionPoint;
    dst_connection_point: StageConnectionPoint;
    path: { x: number | undefined; y: number | undefined; }[];
    node: SVGPolylineElement;
    constructor(src_connection_point: StageConnectionPoint, dst_connection_point: StageConnectionPoint, path: { x: number | undefined; y: number | undefined; }[]) {
        this.src_connection_point = src_connection_point;
        this.dst_connection_point = dst_connection_point;
        this.path = path;
        this.node = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
        let points = [[src_connection_point.x, src_connection_point.y]];
        let x = src_connection_point.x;
        let y = src_connection_point.y;
        for (let path_element of path) {
            if (path_element.x !== undefined) {
                x = path_element.x;
                points.push([x, y]);
            }
            if (path_element.y !== undefined) {
                y = path_element.y;
                points.push([x, y]);
            }
        }
        points.push([dst_connection_point.x, y]);
        points.push([dst_connection_point.x, dst_connection_point.y]);
        let points_str = points.map(v => v.join()).join(" ");
        this.node.setAttribute("class", "connection");
        this.node.setAttribute("points", points_str);
        this.node.textContent = name;
        diagram.appendChild(this.node);
    }
}

let reservation_stations: ReservationStation[] = [];
let setup_stage: SetupStage;
let finish_stage: FinishStage;
let loop_stages: ComputeStage[] = [];
let loop_header_stage: LoopHeaderStage;
let loop_footer_stage: LoopFooterStage;
let next_pc = 0x1000;

function add_instructions() {
    if (instruction_queue.length < 10) {
        let instr = new Instruction(next_pc);
        next_pc += 4;
        instruction_queue.push(instr);
        if (Math.random() < 0.4) {
            let cancel_time = Math.floor(Math.random() * 10) + 1;
            if (!instruction_cancel_queue[cancel_time]) {
                instruction_cancel_queue[cancel_time] = [];
            }
            instruction_cancel_queue[cancel_time]!.push(instr);
        }
    }
}

function cancel_instructions() {
    if (instruction_cancel_queue.length) {
        let first = instruction_cancel_queue.shift();
        if (first) {
            for (let i of first) {
                i.canceled = true;
            }
        }
    }
}

function tick() {
    add_instructions();
    cancel_instructions();
    for (let i of Stage.ALL_STAGES) {
        i.tick_setup();
    }
    for (let i of Stage.ALL_STAGES) {
        i.tick();
    }
    if (instruction_queue[0] === undefined)
        instruction_queue.shift();
    update_visible_state();
}

function update_visible_state() {
    for (let i of Stage.ALL_STAGES) {
        i.update_visible_state();
    }
}

function load() {
    diagram = document.getElementById("diagram")!;
    let loop_stage_count = 3;
    setup_stage = new SetupStage(Stage.GRID_CELL_WIDTH, 2 * Stage.GRID_CELL_HEIGHT);
    let reservation_station_count = 7;
    for (let i = 0; i < 7; i++) {
        let stage = new ReservationStation(0, Stage.GRID_CELL_HEIGHT * i, `rs${i}`);
        reservation_stations.push(stage);
        new Connection(stage.right_connection_point, setup_stage.left_connection_point,
            [{ x: Stage.BOX_WIDTH + 3, y: setup_stage.left_connection_point.y }]);
    }
    loop_header_stage = new LoopHeaderStage(Stage.GRID_CELL_WIDTH * 2, 2 * Stage.GRID_CELL_HEIGHT);
    new Connection(setup_stage.right_connection_point, loop_header_stage.left_connection_point, []);
    let prev_stage = loop_header_stage;
    for (let i = 0; i < loop_stage_count; i++) {
        let stage = new ComputeStage(Stage.GRID_CELL_WIDTH * (3 + i), 2 * Stage.GRID_CELL_HEIGHT, `compute${i}`);
        loop_stages.push(stage);
        new Connection(prev_stage.right_connection_point, stage.left_connection_point, []);
        prev_stage = stage;
    }
    loop_footer_stage = new LoopFooterStage(Stage.GRID_CELL_WIDTH * (3 + loop_stage_count), 2 * Stage.GRID_CELL_HEIGHT);
    new Connection(prev_stage.right_connection_point, loop_footer_stage.left_connection_point, []);
    new Connection(loop_footer_stage.bottom_connection_point, loop_header_stage.bottom_connection_point,
        [{ x: loop_footer_stage.bottom_connection_point.x, y: 3 * Stage.GRID_CELL_HEIGHT + 5 }]);
    finish_stage = new FinishStage(Stage.GRID_CELL_WIDTH * (4 + loop_stage_count), 2 * Stage.GRID_CELL_HEIGHT);
    new Connection(loop_footer_stage.right_connection_point, finish_stage.left_connection_point, []);
    for (let rs of reservation_stations) {
        new Connection(finish_stage.top_connection_point, rs.left_connection_point,
            [{ x: finish_stage.top_connection_point.x, y: -5 }, { x: -7, y: rs.left_connection_point.y }]);
    }
    setInterval(tick, 1500);
    update_visible_state();
}
