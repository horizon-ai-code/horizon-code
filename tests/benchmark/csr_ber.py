"""Run CSR + public-only BER on a benchmark results directory."""
import json, os, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from tests.benchmark.benchmark import load_entries, wrap_code, parse_method_info

STUBS_DIR = os.path.join(os.path.dirname(__file__), "stubs")
JAVAC_FLAGS = ["--release", "25", "-cp", STUBS_DIR]


def tj(token, ptype):
    token = token.strip()
    ptype_l = ptype.lower()
    if ptype_l in ('int','long','double','float','boolean','short','byte'):
        return token
    if ptype_l == 'string':
        return f'"{token}"'
    if ptype == 'ListNode':
        nums = [n.strip() for n in token.strip('[]').split(',') if n.strip()]
        if not nums:
            return 'null'
        # Build linked list using individual constructors
        nodes = [f'new ListNode({n})' for n in nums]
        result = nodes[0]
        for i in range(1, len(nodes)):
            result = f'new ListNode({nums[i]}, {result})' if ptype == 'ListNode' and i == len(nodes) - 1 else result
        # Use append approach: buildList helper
        return f'_bl({",".join(nums)})'
    if token.startswith('[') and token.endswith(']'):
        inner = token[1:-1].strip()
        if inner and ptype_l in ('int[]',):
            return f"new int[]{{{','.join(e.strip() for e in inner.split(','))}}}"
    return token


def parse_tp(text, params):
    text = text.strip().replace('\\[','[').replace('\\]',']').replace('\\n','\n')
    if '=' in text:
        pairs = []; i = 0
        while i < len(text):
            m = re.match(r'(\w+)\s*=\s*', text[i:])
            if not m: break
            name = m.group(1); i += m.end()
            if i < len(text) and text[i] == '[':
                d = 0; j = i
                while j < len(text) and (d > 0 or text[j] == '['):
                    if text[j] == '[': d += 1
                    elif text[j] == ']': d -= 1
                    j += 1
                value = '[' + text[i+1:j-1] + ']' if j > i else text[i:j]; i = j
            elif i < len(text) and text[i] == '"':
                j = i+1
                while j < len(text) and text[j] != '"': j += 1
                value = text[i:j+1]; i = j+1
            else:
                j = i
                while j < len(text) and text[j] not in (',','\n'): j += 1
                value = text[i:j].strip(); i = j
            pairs.append((name, value))
            while i < len(text) and text[i] in (',',' ','\n','\t'): i += 1
        if pairs: return pairs
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return [(params[min(idx, len(params)-1)][1], line) for idx, line in enumerate(lines)]


def check_entry(e, td):
    num = e.get("num", 0)
    final = e.get("final_code", "")
    unchanged = e.get("code_unchanged", False)

    csr_ok = False
    ber_ok = False
    pub_in = None

    # CSR
    if not unchanged and final:
        wrapped = wrap_code(final)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(wrapped)
            src = f.name
        try:
            r = subprocess.run(["javac"] + JAVAC_FLAGS + [src], capture_output=True, text=True, timeout=15)
            csr_ok = r.returncode == 0
        except FileNotFoundError:
            print("  javac not found")
            csr_ok = False
        except subprocess.TimeoutExpired:
            print("  javac timeout")
        finally:
            try: os.unlink(src)
            except: pass

    # BER (public only)
    if csr_ok and td:
        raw_in = td.get("public_tests_input", "")
        raw_out = td.get("public_tests_output", "")
        pub_in = raw_in.strip()
        pub_out = raw_out.strip()

        if pub_in and pub_out:
            info = parse_method_info(final)
            if info:
                method_name, params = info
                wrapped = wrap_code(final)
                class_name = "Wrapper"
                for m in re.finditer(r'class\s+(\w+)\s*\{', wrapped):
                    class_name = m.group(1)

                pairs = parse_tp(pub_in, params)
                args = []
                for ptype, pname in params:
                    token = ""
                    for tn, tv in pairs:
                        if tn.lower() == pname.lower():
                            token = tv
                            break
                    args.append(tj(token, ptype) if token else 'null')

                call = f'new {class_name}().{method_name}({",".join(args)})'

                bl_def = "static ListNode _bl(int... v){" + \
                    "if(v.length==0)return null;" + \
                    "ListNode h=new ListNode(v[0]);ListNode c=h;" + \
                    "for(int i=1;i<v.length;i++){" + \
                    "c.next=new ListNode(v[i]);c=c.next;}" + \
                    "return h;}"

                nv_def = "static int _nv(ListNode n) {" + \
                    'for(String fn:new String[]{"val","value"}){' + \
                    "try{" + \
                    "java.lang.reflect.Field f=n.getClass().getDeclaredField(fn);" + \
                    "f.setAccessible(true);return f.getInt(n);" + \
                    "}catch(Exception e){}" + \
                    "}" + \
                    "return -1;}"

                pr_def = "static String _pr(Object o){" + \
                    'if(o==null)return"null";' + \
                    "if(o instanceof ListNode){" + \
                    'StringBuilder sb=new StringBuilder("[");' + \
                    "ListNode n=(ListNode)o;" + \
                    "while(n!=null){" + \
                    "sb.append(_nv(n));n=n.next;" + \
                    "if(n!=null)sb.append(',');" + \
                    "}" + \
                    'sb.append("]");return sb.toString();' + \
                    "}" + \
                    "if(o instanceof int[]){" + \
                    "int[] a=(int[])o;" + \
                    'StringBuilder sb=new StringBuilder("[");' + \
                    "for(int i=0;i<a.length;i++){" + \
                    "sb.append(a[i]);" + \
                    "if(i<a.length-1)sb.append(',');" + \
                    "}" + \
                    'sb.append("]");return sb.toString();' + \
                    "}" + \
                    "return o.toString();}"

                helpers = bl_def + nv_def + pr_def
                main_body = 'System.out.println(_pr(' + call + '));'
                tw = "class _BW_{" + helpers + "public static void main(String[]a){" + main_body + "}}"

                combined = 'import java.util.*;\n' + wrapped.strip() + '\n' + tw
                with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                    f.write(combined)
                    src = f.name
                try:
                    r = subprocess.run(["javac"] + JAVAC_FLAGS + [src], capture_output=True, text=True, timeout=15)
                    if r.returncode == 0:
                        tmpdir = os.path.dirname(src)
                        r2 = subprocess.run(["java", "-cp", f"{tmpdir}:{STUBS_DIR}", "_BW_"],
                                            capture_output=True, text=True, timeout=10)
                        actual = r2.stdout.strip().replace('\n','').replace(' ','')
                        expected = pub_out.strip().replace('\n','').replace(' ','').replace('\\[','[').replace('\\]',']')
                        if actual == expected:
                            ber_ok = True
                except FileNotFoundError:
                    pass
                except subprocess.TimeoutExpired:
                    pass
                finally:
                    try: os.unlink(src)
                    except: pass

    return {"num": num, "csr": csr_ok, "ber": ber_ok, "has_input": bool(pub_in), "unchanged": unchanged}


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="tests/benchmark/single")
    p.add_argument("--dataset", default="tests/benchmark/data/dataset_final.json")
    args = p.parse_args()

    entries = load_entries(args.dir)
    dataset = {}
    if os.path.exists(args.dataset):
        with open(args.dataset) as f:
            for de in json.load(f):
                dataset[de["num"]] = de

    print(f"Checking {len(entries)} entries from {args.dir}")
    results = []
    for idx, e in enumerate(entries):
        num = e.get("num", 0)
        td = dataset.get(num)
        r = check_entry(e, td)
        results.append(r)
        marks = f"{'✓' if r['csr'] else '✗'}|{'✓' if r['ber'] else '✗'}ber" if r['csr'] else f"{'✓' if r['csr'] else '✗'}csr"
        print(f"[{idx+1:3d}/{len(entries)}] #{num}  {marks}")

    total = len(results)
    csr_good = sum(1 for r in results if r['csr'])
    ber_good = sum(1 for r in results if r['ber'])
    ber_total = sum(1 for r in results if r['has_input'] and r['csr'])

    print(f"\n{'='*45}")
    print(f"CSR: {csr_good}/{total} ({csr_good*100//total}%)")
    print(f"BER (public only): {ber_good}/{ber_total} ({ber_good*100//max(1,ber_total)}%)")
    print(f"Overall valid: {ber_good}/{total} ({ber_good*100//total}%) — code compiles AND passes public test")


if __name__ == "__main__":
    main()
