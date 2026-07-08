/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:5000/api/:path*',
      },
      {
        source: '/deployments.json',
        destination: 'http://127.0.0.1:5000/deployments.json',
      },
    ];
  },
};

export default nextConfig;
