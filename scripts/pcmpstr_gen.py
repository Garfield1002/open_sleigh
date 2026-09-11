"""PCMP{E,I}STR{I,M}: a Python model of the SDM semantics (validated against the
Binit captures) and a generator of the equivalent SLEIGH."""
import sys, json, collections

# ---------------------------------------------------------------- model
def elems(v128, w):
    return [(v128 >> (i*w*8)) & ((1 << (w*8)) - 1) for i in range(16 // w)]

def to_signed(x, bits):
    return x - (1 << bits) if x >> (bits - 1) else x

def explicit_len(r, n):
    r &= 0xffffffff
    s = to_signed(r, 32)
    a = -s if s < 0 else s          # INT_MIN stays 0x80000000, saturates
    return min(a, n)

def implicit_len(e, n):
    for i, x in enumerate(e):
        if x == 0: return i
    return n

def model(a, b, imm, explicit, eax=0, edx=0):
    w = 2 if imm & 1 else 1
    n = 16 // w
    bits = w * 8
    signed = (imm >> 1) & 1
    ea, eb = elems(a, w), elems(b, w)
    la = explicit_len(eax, n) if explicit else implicit_len(ea, n)
    lb = explicit_len(edx, n) if explicit else implicit_len(eb, n)
    mode = (imm >> 2) & 3
    res1 = 0
    if mode == 0:
        for j in range(lb):
            if any(ea[i] == eb[j] for i in range(la)): res1 |= 1 << j
    elif mode == 1:
        cv = (lambda x: to_signed(x, bits)) if signed else (lambda x: x)
        for j in range(lb):
            for i in range(0, n, 2):
                if i + 1 < la and cv(ea[i]) <= cv(eb[j]) <= cv(ea[i+1]):
                    res1 |= 1 << j; break
    elif mode == 2:
        for j in range(n):
            va, vb = j < la, j < lb
            if (va and vb and ea[j] == eb[j]) or (not va and not vb): res1 |= 1 << j
    else:
        for j in range(n):
            ok = True
            for i in range(la):
                k = j + i
                if k >= n: break                      # needle runs past the register: not compared
                if k >= lb or ea[i] != eb[k]: ok = False; break
            if ok: res1 |= 1 << j
    full = (1 << n) - 1
    pol = (imm >> 4) & 3
    if pol == 1: res2 = res1 ^ full
    elif pol == 3: res2 = res1 ^ ((1 << lb) - 1)
    else: res2 = res1
    res2 &= full
    ecx = xmm0 = None
    if res2 == 0: ecx = n
    elif imm & 0x40: ecx = res2.bit_length() - 1
    else: ecx = (res2 & -res2).bit_length() - 1
    if imm & 0x40:
        xmm0 = 0
        for j in range(n):
            if (res2 >> j) & 1: xmm0 |= ((1 << bits) - 1) << (j * bits)
    else:
        xmm0 = res2
    flags = {'CF': int(res2 != 0), 'ZF': int(lb < n), 'SF': int(la < n), 'OF': res2 & 1, 'AF': 0, 'PF': 0}
    return res2, ecx, xmm0, flags

FLAGBIT = {'CF': 0, 'PF': 2, 'AF': 4, 'ZF': 6, 'SF': 7, 'OF': 11}

def check(rows_path):
    bad = collections.Counter(); ok = collections.Counter(); ex = {}
    for line in open(rows_path):
        if not line.strip(): continue
        ins, init, fin = line.rstrip('\n').split('|', 2)
        mn = ins.split()[0]
        imm = int(ins.split(',')[-1], 16) & 0xff
        init = json.loads(init); fin = json.loads(fin)
        a = int.from_bytes(bytes.fromhex(init['xmm1']), 'little')
        src = ins.split(',')[1].strip()
        if src.startswith('xmm'):
            b = int.from_bytes(bytes.fromhex(init[src]), 'little')
        else:
            sm = bytes.fromhex(init['scratch_memory']); b = int.from_bytes(sm[256:272], 'little')
        explicit = mn.startswith('pcmpe')
        eax = int(init.get('rax', 0), 0) if isinstance(init.get('rax', 0), str) else init.get('rax', 0)
        edx = int(init.get('rdx', 0), 0) if isinstance(init.get('rdx', 0), str) else init.get('rdx', 0)
        res2, ecx, xmm0, flags = model(a, b, imm, explicit, eax, edx)
        fl = fin['flag']
        got_flags = {k: (fl >> v) & 1 for k, v in FLAGBIT.items()}
        want = {}
        if mn.endswith('i'):
            got = fin['rcx'] & 0xffffffffffffffff
            want['rcx'] = (ecx, got)
        else:
            got = int.from_bytes(bytes.fromhex(fin['xmm0']), 'little')
            want['xmm0'] = (xmm0, got)
        want['flags'] = (flags, got_flags)
        key = (mn, imm)
        good = all(w == g for w, g in want.values())
        (ok if good else bad)[key] += 1
        if not good: ex.setdefault(key, (ins, init.get('rax'), init.get('rdx'), init['xmm1'], src, want))
    print('ok', sum(ok.values()), 'bad', sum(bad.values()))
    for k, v in sorted(bad.items()): print(' ', k, v, ex[k])

# ---------------------------------------------------------------- sleigh
def emit():
    out = []
    P = out.append
    P('''# PCMP{E,I}STR{I,M}: the aggregation (imm8 bits 2-3) and the element width
# (bit 0) are runtime branches in each constructor, so only the selected
# comparison block executes; the polarity and the output form are selects.
# Equal-ordered matches the needle (first operand) against the haystack
# (second) at every offset j; a needle element past the haystack's length is
# a mismatch, past the register's end it is simply not compared, and an
# invalid needle element matches anything. Validated against every captured
# register-form state (693k) with a Python model of the same rules. `va`/`vb` are validity masks (bit i set when element i is
# inside its string's length); the lengths come from the first null element
# (I forms) or from |EAX|/|EDX| saturated at the element count (E forms).
''')
    for w, n, W in ((1, 16, 'b'), (2, 8, 'w')):
        bits = w * 8
        full = (1 << n) - 1
        fullc = f"0x{full:x}:2"
        # implicit lengths: prefix AND of non-null elements
        P(f"macro pcmpstr_implicit_{W}(v, valid) {{")
        P(f"    local s:16 = v;")
        P(f"    local ok:1 = 1;")
        P(f"    local m:2 = 0;")
        for i in range(n):
            P(f"    ok = ok && (s[{i*bits},{bits}] != 0); m = m | (zext(ok) << {i});")
        P(f"    valid = m;")
        P("}\n")
        P(f"macro pcmpstr_explicit_{W}(r, valid) {{")
        P(f"    local x:4 = r;")
        P(f"    local neg:4 = 0 - x;")
        P(f"    local mag:4; conditionalAssign(mag, x s< 0, neg, x);")
        P(f"    local len:4; conditionalAssign(len, mag > {n}, {n}:4, mag);")
        P(f"    local m:4 = (1:4 << len) - 1;")
        P(f"    valid = m:2;")
        P("}\n")
        # aggregation macros
        for mode, name in ((0, 'any'), (1, 'ranges'), (2, 'each'), (3, 'ordered')):
            variants = [('', '<=')] if mode != 1 else [('', '<='), ('s', 's<=')]
            for sfx, le in variants:
                P(f"macro pcmpstr_{name}{sfx}_{W}(res, a, b, va, vb) {{")
                P(f"    local x:16 = a;")
                P(f"    local y:16 = b;")
                P(f"    local m:2 = 0;")
                P(f"    local t:1;")
                if mode == 0:
                    for j in range(n):
                        terms = " || ".join(f"(x[{i*bits},{bits}] == y[{j*bits},{bits}] && va[{i},1])" for i in range(n))
                        P(f"    t = ({terms}) && vb[{j},1]; m = m | (zext(t) << {j});")
                elif mode == 1:
                    for j in range(n):
                        terms = " || ".join(f"(x[{i*bits},{bits}] {le} y[{j*bits},{bits}] && y[{j*bits},{bits}] {le} x[{(i+1)*bits},{bits}] && va[{i+1},1])" for i in range(0, n, 2))
                        P(f"    t = ({terms}) && vb[{j},1]; m = m | (zext(t) << {j});")
                elif mode == 2:
                    for j in range(n):
                        P(f"    t = (x[{j*bits},{bits}] == y[{j*bits},{bits}] && va[{j},1] && vb[{j},1]) || (!va[{j},1] && !vb[{j},1]); m = m | (zext(t) << {j});")
                else:
                    for j in range(n):
                        terms = []
                        for i in range(n - j):
                            k = j + i
                            terms.append(f"(!va[{i},1] || (x[{i*bits},{bits}] == y[{k*bits},{bits}] && vb[{k},1]))")
                        P(f"    t = {' && '.join(terms)}; m = m | (zext(t) << {j});")
                P(f"    res = m;")
                P("}\n")
        # polarity, output, flags
        P(f"macro pcmpstr_polarity_{W}(res, ctl, vb) {{")
        P(f"    local c:1 = ctl;")
        P(f"    local flip:2; conditionalAssign(flip, c[5,1], vb, {fullc});")
        P(f"    local flipped:2 = res ^ flip;")
        P(f"    conditionalAssign(res, c[4,1], flipped, res);")
        P("}\n")
        P(f"macro pcmpstr_index_{W}(idx, res, ctl) {{")
        P(f"    local c:1 = ctl;")
        P(f"    local r:2 = res;")
        P(f"    local lsb:4 = {n};")
        for j in reversed(range(n)):
            P(f"    conditionalAssign(lsb, r[{j},1], {j}:4, lsb);")
        P(f"    local msb:4 = {n};")
        for j in range(n):
            P(f"    conditionalAssign(msb, r[{j},1], {j}:4, msb);")
        P(f"    conditionalAssign(idx, c[6,1], msb, lsb);")
        P("}\n")
        P(f"macro pcmpstr_mask_{W}(out, res, ctl) {{")
        P(f"    local c:1 = ctl;")
        P(f"    local r:2 = res;")
        P(f"    local expanded:16 = 0;")
        for j in range(n):
            P(f"    expanded[{j*bits},{bits}] = 0 - zext(r[{j},1]);")
        P(f"    local narrow:16 = zext(r);")
        P(f"    conditionalAssign(out, c[6,1], expanded, narrow);")
        P("}\n")
        P(f"macro pcmpstr_flags_{W}(res, va, vb) {{")
        P(f"    CF = res != 0;")
        P(f"    ZF = vb != {fullc};")
        P(f"    SF = va != {fullc};")
        P(f"    OF = res[0,1];")
        P(f"    AF = 0;")
        P(f"    PF = 0;")
        P("}\n")
    # constructors: the immediate cannot be constrained after the ellipsis
    # operand, so the element width and the aggregation are runtime branches;
    # only the selected path executes.
    ops = {'PCMPESTRM': 0x60, 'PCMPESTRI': 0x61, 'PCMPISTRM': 0x62, 'PCMPISTRI': 0x63}
    for mn, op in ops.items():
        explicit = mn[4] == 'E'
        index = mn.endswith('I')
        dest_pat = "check_ECX_dest & " if index else ""
        P(f":{mn} XmmReg1, XmmReg2_m128, imm8 is vexMode=0 & $(PRE_66) & byte=0x0F; byte=0x3A; byte=0x{op:02x}; ({dest_pat}XmmReg2_m128 & XmmReg1 ...); imm8")
        P("{")
        P("    local ctl:1 = imm8;")
        P("    local a:16 = XmmReg1;")
        P("    local b:16 = XmmReg2_m128;")
        P("    local mode:1 = (ctl >> 2) & 3;")
        P("    local va:2; local vb:2; local res:2;")
        P("    local idx:4 = 0;" if index else "    local out:16 = 0;")
        P("    if ((ctl & 1) != 0) goto <words>;")
        for W in ('b', 'w'):
            if W == 'w': P("<words>")
            if explicit:
                P(f"    pcmpstr_explicit_{W}(EAX, va);")
                P(f"    pcmpstr_explicit_{W}(EDX, vb);")
            else:
                P(f"    pcmpstr_implicit_{W}(a, va);")
                P(f"    pcmpstr_implicit_{W}(b, vb);")
            P(f"    if (mode != 0) goto <{W}_ranges>;")
            P(f"    pcmpstr_any_{W}(res, a, b, va, vb);")
            P(f"    goto <{W}_done>;")
            P(f"<{W}_ranges>")
            P(f"    if (mode != 1) goto <{W}_each>;")
            P(f"    if ((ctl & 2) != 0) goto <{W}_sranges>;")
            P(f"    pcmpstr_ranges_{W}(res, a, b, va, vb);")
            P(f"    goto <{W}_done>;")
            P(f"<{W}_sranges>")
            P(f"    pcmpstr_rangess_{W}(res, a, b, va, vb);")
            P(f"    goto <{W}_done>;")
            P(f"<{W}_each>")
            P(f"    if (mode != 2) goto <{W}_ordered>;")
            P(f"    pcmpstr_each_{W}(res, a, b, va, vb);")
            P(f"    goto <{W}_done>;")
            P(f"<{W}_ordered>")
            P(f"    pcmpstr_ordered_{W}(res, a, b, va, vb);")
            P(f"<{W}_done>")
            P(f"    pcmpstr_polarity_{W}(res, ctl, vb);")
            if index:
                P(f"    pcmpstr_index_{W}(idx, res, ctl);")
            else:
                P(f"    pcmpstr_mask_{W}(out, res, ctl);")
            P(f"    pcmpstr_flags_{W}(res, va, vb);")
            if W == 'b': P("    goto <end>;")
        P("<end>")
        if index:
            P("    ECX = idx;")
            P("    build check_ECX_dest;")
        else:
            P("    XMM0 = out;")
        P("}\n")
    return "\n".join(out)

if __name__ == '__main__':
    if sys.argv[1] == 'check': check(sys.argv[2])
    else: sys.stdout.write(emit())
