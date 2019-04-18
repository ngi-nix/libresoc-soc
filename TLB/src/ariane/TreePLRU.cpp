#include <cstdint>
#include <iostream>
#include <cmath>


#define NWAY 8
#define NLINE 256
#define HIT 0
#define MISS 1
#define MS 1000
/*
Detailed TreePLRU inference see here: https://docs.google.com/spreadsheets/d/14zQpPYPwDAbCCjBT_a3KLaE5FEk-RNhI8Z7Qm_biW8g/edit?usp=sharing
Ref: https://people.cs.clemson.edu/~mark/464/p_lru.txt
four-way set associative - three bits
   each bit represents one branch point in a binary decision tree; let 1
   represent that the left side has been referenced more recently than the
   right side, and 0 vice-versa
              are all 4 lines valid?
                   /       \
                 yes        no, use an invalid line
                  |
                  |
                  |
             bit_0 == 0?            state | replace      ref to | next state
              /       \             ------+--------      -------+-----------
             y         n             00x  |  line_0      line_0 |    11_
            /           \            01x  |  line_1      line_1 |    10_
     bit_1 == 0?    bit_2 == 0?      1x0  |  line_2      line_2 |    0_1
       /    \          /    \        1x1  |  line_3      line_3 |    0_0
      y      n        y      n
     /        \      /        \        ('x' means       ('_' means unchanged)
   line_0  line_1  line_2  line_3      don't care)
 8-way set associative - 7  = 1+2+4 bits
16-way set associative - 15 = 1+2+4+8 bits
32-way set associative - 31 = 1+2+4+8+16 bits
64-way set associative - 63 = 1+2+4+8+16+32 bits
*/
using namespace std;
struct AddressField {
    uint64_t wd_idx : 2;//Unused
    uint64_t offset : 4;//Unused
    uint64_t index  : 8;//NLINE = 256 = 2^8
    uint64_t tag    : 50;
};

union Address {
    uint32_t* p;
    AddressField fields;
};

struct Cell {
    bool v;
    uint64_t tag;

    Cell() : v(false), tag(0) {}

    bool isHit(uint64_t tag) {
        return v && (tag == this->tag);
    }

    void fetch(uint32_t* address) {
        Address addr;
        addr.p = address;
        addr.fields.offset = 0;
        addr.fields.wd_idx = 0;
        tag = addr.fields.tag;
        v = true;
    }
};

ostream& operator<<(ostream & out, const Cell& cell) {
    out << " v:" << cell.v << " tag:" << hex << cell.tag;
    return out;
}

struct Block {
    Cell cell[NWAY];
    uint32_t state;
    uint64_t *mask;//Mask the state to get accurate value for specified 1 bit.
    uint64_t *value;
    uint64_t *next_value;

    Block() : state(0) {
        switch (NWAY) {
            case 4:
                mask = new uint64_t[4]{0b110, 0b110, 0b101, 0b101};
                value = new uint64_t[4]{0b000, 0b010, 0b100, 0b101};
                next_value = new uint64_t[4]{0b110, 0b100, 0b001, 0b000};
                break;
            case 8:
                mask = new uint64_t[8]{0b1101000, 0b1101000, 0b1100100, 0b1100100, 0b1010010, 0b1010010, 0b1010001,
                                       0b1010001};
                value = new uint64_t[8]{0b0000000, 0b0001000, 0b0100000, 0b0100100, 0b1000000, 0b1000010, 0b1010000,
                                        0b1010001};
                next_value = new uint64_t[8]{0b1101000, 0b1100000, 0b1000100, 0b1000000, 0b0010010, 0b0010000,
                                             0b0000001, 0b0000000};
                break;
                //TODO - more NWAY goes here.
            default:
                std::cout << "Error definition NWAY = " << NWAY << std::endl;
        }
    }

    uint32_t *getByTag(uint64_t tag, uint32_t *pway) {
        for (int i = 0; i < NWAY; ++i) {
            if (cell[i].isHit(tag)) {
                *pway = i;
                return pway;
            }
        }
        return NULL;
    }

    void setLRU(uint32_t *address) {
        int way = 0;
        uint32_t st = state;
        for (int i = 0; i < NWAY; ++i) {
            if ((state & mask[i]) == value[i]) {
                state ^= mask[i];
                way = i;
                break;
            }
        }
        cell[way].fetch(address);
        cout << "MISS: way:" << way << " address:" << address << " state:" << st << "->" << state << endl;
    }

    uint32_t *get(uint32_t *address, uint32_t *pway) {
        Address addr;
        addr.p = address;
        uint32_t *d = getByTag(addr.fields.tag, pway);
        if (d != NULL) {
            return &d[addr.fields.offset];
        }
        return d;
    }

    int set(uint32_t *address) {
        uint32_t way = 0;
        uint32_t *p = get(address, &way);
        if (p != NULL) {
            printf("HIT: address:%p ref_to way:%d state %X --> ", address, way, state);
            state &= ~mask[way];
            printf("%X --> ", state);
            state |= next_value[way];
            printf("%X\n", state);
            // *p = *address; //skip since address is fake.
            return HIT;
        } else {
            setLRU(address);
            return MISS;
        }
    }
};

ostream& operator<<(ostream & out, const Block& block) {
    out << "state:" << block.state << " ";
    for (int i = 0; i<NWAY; i++) {
        out << block.cell[i];
    }
    return out;
}

struct Cache {
    Block block[NLINE];
    uint32_t count[2];
    Cache() { count[HIT] = 0; count[MISS] = 0; }

    void access(uint32_t* address) {
        Address addr;
        addr.p = address;
        Block& b = block[addr.fields.index];
        ++count[b.set(address)];
    }

};
ostream& operator<<(ostream & out, const Cache& cache) {
    out << "\n==Summary==\n\tHit: " << cache.count[HIT] <<  " Miss: " << cache.count[MISS] << std::endl;
    for (int i = 0; i < NLINE; i++) {
        out << cache.block[i] << endl;
    }
    return out;
}

Cache cache;
void multiply(uint32_t* m1, uint32_t* m2, uint32_t* res)
{
    int x, i, j;
    for (i = 0; i < MS; i++) {
        for (j = 0; j < MS; j++) {
            cache.access(res + i*MS +j);
            for (x = 0; x < MS; x++) {
                cache.access(m1 + i*MS + x);
                cache.access(m2 + x*MS + j);
                cache.access(res + i*MS +j);
                // res[i][j] += m1[i][x] * m2[x][j];
                cache.access(res + i*MS +j);
            }
        }
    }
}

int main()
{
    uint32_t* m1 = (uint32_t*) 0xFACE00A000000000LL;  // fake virtual address; don’t access it
    uint32_t* m2 = (uint32_t*) 0xFACE00B000000000LL;  // fake virtual address; don’t access it
    uint32_t* res =  (uint32_t*) 0xFACE00C000000000LL; // fake virtual address; don’t access it
    multiply(m1, m2, res);
    cout << cache << endl;
    return 0;
}