#!/usr/bin/env python

import getopt
import itertools
import sys
import struct
import StringIO as stringio

import utils


def usage():
    print """
bpf_dns.py [ OPTIONS ] [ domain... ]

This tool creates a raw Berkeley Packet Filter (BPF) rule that will
match packets which are DNS queries against listed domains. For
example:

  bpf.py example.com

will print a BPF rule matching all packets that look like a DNS packet
first query being equal to "example.com". Another example:

  bpf.py *.www.fint.me

will matchd packets that have a any prefix (subdomain) and exactly
"www.fint.me" as suffix. It will match:

    blah.www.fint.me
    anyanyany.www.fint.me

but it will not match:

   www.fint.me
   blah.blah.www.fint.me

Also, star has a special meaning only if it's a sole part of
subdomain: "*xxx.example.com" is treated as a literal star, so is
"xxx*.example.com". On the other hand "xxx.*.example.com" will have a
wildcard meaning.

You can create a single rule matching than one domain:

  bpf.py example.com *.www.fint.me

Leading and trailing dots are ignored, this commands are equivalent:

  bpf.py example.com fint.me
  bpf.py .example.com fint.me.

Options are:
  -h, --help         print this message
  -n, --negate       capture packets that don't match given domains
  -i, --ignore-case  make the rule case insensitive. use with care.
  -s, --assembly     print BPF assembly instead of byte code
""".lstrip()
    sys.exit(2)


def find_binary(prefixes, name, args):
    for prefix in prefixes:
        try:
            subprocess.call([os.path.join(prefix, name)] + args)
        except OSError, e:
            continue
        return prefix
    print >> sys.stderr, prefix, "%r tool not found in your PATH" % (name,)
    os._exit(-2)



def main():
    ignorecase = negate = assembly = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hins",
                                   ["help", "ignore-case", "negate", "assembly"])
    except getopt.GetoptError as err:
        print str(err)
        usage()

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-i", "--ignore-case"):
            ignorecase = True
        elif o in ("-n", "--negate"):
            negate = True
        elif o in ("-s", "--assembly"):
            assembly = True
        else:
            assert False, "unhandled option"

    if not args:
        print >> sys.stderr, "At least one domain name required."
        sys.exit(-1)

    if not assembly:
        sys.stdout, saved_stdout = stringio.StringIO(), sys.stdout


    list_of_rules = []

    for domain in args:
        # remove trailing and leading dots and whitespace
        domain = domain.strip(".").strip()

        # keep the trailing dot
        domain += '.'

        rule = []
        for part in domain.split("."):
            if part == '*':
                rule.append( (False, '*') )
            else:
                rule.append( (True, chr(len(part)) + part) )

        list_of_rules.append( list(merge(rule)) )

    def match_exact(s, label):
        print "    ; %r" % s
        off = 0
        while s:
            if len(s) >= 4:
                m, s = s[:4], s[4:]
                m, = struct.unpack('!I', m)
                print "    ld [x + %i]" % off
                if ignorecase:
                    print "    or #0x20202020"
                    m |= 0x20202020
                print "    jneq #0x%08x, %s" % (m, label,)
                off += 4
            elif len(s) >= 2:
                m, s = s[:2], s[2:]
                m, = struct.unpack('!H', m)
                print "    ldh [x + %i]" % off
                if ignorecase:
                    print "    or #0x2020"
                    m |= 0x2020
                print "    jneq #0x%04x, %s" % (m, label,)
                off += 2
            else:
                m, s = s[:1], s[1:]
                m, = struct.unpack('!B', m)
                print "    ldb [x + %i]" % off
                if ignorecase:
                    print "    or #0x20"
                    m |= 0x20
                print "    jneq #0x%02x, %s" % (m, label,)
                off += 1
        print "    txa"
        print "    add #%i" % (off,)
        print "    tax"

    def match_star():
        print "    ; Match: *"
        print "    ldb [x + 0]"
        print "    add x"
        print "    add #1"
        print "    tax"

    print "    ldx 4*([14]&0xf)"
    print "    txa"
    print "    add #34"
    print "    ; M[0] = offset of first dns query byte"
    print "    st M[0]"
    print

    for i, rules in enumerate(list_of_rules):
        print "lb_%i:" % (i,)
        print "    ; %r" % (rules,)
        print "    ldx M[0]"
        for x in rules:
            if x != '*':
                match_exact(x, 'lb_%i' % (i+1,))
            else:
                match_star()
        print "    ret #%i" % (1 if not negate else 0)
        print

    print "lb_%i:" % (i+1,)
    print "    ret #%i" % (0 if not negate else 1)


    sys.stdout.flush()

    if not assembly:
        assembly = sys.stdout.seek(0)
        assembly = sys.stdout.read()
        sys.stdout = saved_stdout
        print utils.bpf_compile(assembly)


# Accepts list of tuples [(mergeable, value)] and merges fields where
# mergeable is True.
def merge(iterable, merge=lambda a,b:a+b):
    for k, g in itertools.groupby(iterable, key=lambda a:a[0]):
        if k is True:
            yield reduce(merge, (i[1] for i in g))
        else:
            for i in g:
                yield i[1]


if __name__ == "__main__":
    main()