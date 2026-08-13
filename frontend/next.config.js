/** @type {import('next').NextConfig} */
const nextConfig = {
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
