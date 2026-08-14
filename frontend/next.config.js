/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Pin the Turbopack root to the frontend dir so standalone output is flat
  // (.next/standalone/server.js) instead of nested. Critical for Docker builds.
  turbopack: {
    root: __dirname,
  },
  // Proxy API requests to Flask backend (internal port 5000)
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.FLASK_URL || 'http://127.0.0.1:5000'}/api/:path*`,
      },
      {
        source: '/app/api/:path*',
        destination: `${process.env.FLASK_URL || 'http://127.0.0.1:5000'}/app/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
