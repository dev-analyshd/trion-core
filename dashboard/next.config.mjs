/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:5001/api/:path*',
      },
      {
        source: '/deployments.json',
        destination: 'http://127.0.0.1:5001/deployments.json',
      },
    ];
  },
};

export default nextConfig;
