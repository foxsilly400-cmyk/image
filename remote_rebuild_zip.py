import zipfile, os
base = '/root/autodl-tmp/genui'
entries = ['.gitignore', 'README.md', 'app.py', 'online_app.js', 'patch_stack.py',
           'static/app.js', 'static/style.css', 'tags.csv',
           'templates/index.html', 'templates/login.html',
           'test_cn.py', 'test_diag.py', 'test_gen.py', 'test_gen2.py',
           'test_mobile.py', 'test_new.py', 'test_persist.py', 'test_queue.py',
           'test_rb.py', 'test_rgz.py', 'test_ui.py', 'test_ui2.py',
           'test_ui3.py', 'test_ui4.py', 'test_upscale.py']
with zipfile.ZipFile('/root/autodl-tmp/genui.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for e in entries:
        p = os.path.join(base, e)
        if os.path.exists(p):
            z.write(p, e)
        else:
            print('MISSING', e)
print('zip rebuilt, entries:', len(entries))
