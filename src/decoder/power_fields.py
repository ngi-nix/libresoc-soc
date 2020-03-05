def decode_fields():
    with open("fields.txt") as f:
        txt = f.readlines()
    forms = {}
    reading_data = False
    for l in txt:
        print ("line", l)
        l = l.strip()
        if len(l) == 0:
            continue
        if reading_data:
            if l[0] == '#':
                reading_data = False
            else:
                forms[heading].append(l)
        if not reading_data:
            assert l[0] == '#'
            heading = l[1:].strip()
            if heading.startswith('1.6.28'): # skip instruction fields for now
                break
            heading = heading.split(' ')[-1]
            print ("heading", heading)
            reading_data = True
            forms[heading] = []

    res = {}
    for hdr, form in forms.items():
        print ("heading", hdr)
        res[hdr] = decode_form(form)
    return res

def decode_form_header(hdr):
    res = {}
    count = 0
    hdr = hdr.strip()
    print (hdr.split('|'))
    for f in hdr.split("|"):
        if not f:
            continue
        if f[0].isdigit():
            idx = int(f.strip().split(' ')[0])
            res[count] = idx
        count += len(f) + 1
    return res

def decode_line(header, line):
    line = line.strip()
    res = {}
    count = 0
    print ("line", line)
    prev_fieldname = None
    for f in line.split("|"):
        if not f:
            continue
        end = count + len(f) + 1
        fieldname = f.strip()
        if not fieldname or fieldname.startswith('/'):
            count = end
            continue
        bitstart = header[count]
        if prev_fieldname is not None:
            res[prev_fieldname] = (res[prev_fieldname], bitstart)
        res[fieldname] = bitstart
        count = end
        prev_fieldname = fieldname
    res[prev_fieldname] = (bitstart, 32)
    return res

def decode_form(form):
    header = decode_form_header(form[0])
    res = []
    print ("header", header)
    for line in form[1:]:
        dec = decode_line(header, line)
        if dec:
            res.append(dec)
    return res

    
if __name__ == '__main__':
    forms = decode_fields()
    for hdr, form in forms.items():
        print ()
        print (hdr)
        for l in form:
            print ("line", l)
            for k, v in l.items():
                print ("%s: %d-%d" % (k, v[0], v[1]))
