const esbuild = require('esbuild');
const path = require('path');

const isWatch = process.argv.includes('--watch');

const shared = {
  bundle: true,
  minify: !isWatch,
  sourcemap: isWatch,
  target: ['es2020'],
};

const outdir = path.join(__dirname, 'server', 'static', 'dist');

async function build() {
  const configs = [
    { entryPoints: ['src/js/analysis/app.js'], outfile: path.join(outdir, 'analysis.min.js'), format: 'iife' },
    { entryPoints: ['src/js/library/library-app.js'], outfile: path.join(outdir, 'library.min.js'), format: 'iife' },
    { entryPoints: ['src/css/analysis-bundle.css'], outfile: path.join(outdir, 'analysis.min.css') },
    { entryPoints: ['src/css/library-bundle.css'], outfile: path.join(outdir, 'library.min.css') },
  ];

  const contexts = [];
  for (const cfg of configs) {
    contexts.push(await esbuild.context({ ...shared, ...cfg }));
  }

  if (isWatch) {
    await Promise.all(contexts.map(ctx => ctx.watch()));
    console.log('Watching for changes...');
  } else {
    await Promise.all(contexts.map(ctx => ctx.rebuild()));
    await Promise.all(contexts.map(ctx => ctx.dispose()));
    console.log('Build complete.');
  }
}

build().catch(() => process.exit(1));
