/**
 * Luna Agent — Cloudflare Worker
 * Serves the landing page at lunaagent.dev
 */
import html from './index.html';

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Serve the landing page on GET /
    if (request.method === 'GET' && (url.pathname === '/' || url.pathname === '')) {
      return new Response(html, {
        headers: {
          'Content-Type': 'text/html;charset=UTF-8',
          'Cache-Control': 'public, max-age=300, stale-while-revalidate=60',
          'X-Content-Type-Options': 'nosniff',
          'X-Frame-Options': 'DENY',
          'Referrer-Policy': 'strict-origin-when-cross-origin',
        },
      });
    }

    // Redirect /index.html → /
    if (url.pathname === '/index.html') {
      return Response.redirect(`${url.origin}/`, 301);
    }

    // 404 for everything else
    return new Response('Not Found', {
      status: 404,
      headers: { 'Content-Type': 'text/plain' },
    });
  },
};
