import { describe, expect, it, vi } from 'vitest'
import { streamAgent } from './api'

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

describe('streamAgent', () => {
  it('parses SSE events even when chunks split an event boundary', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      'event: progress\ndata: {"sequence":1,"node":"class',
      'ify","status":"succeeded","detail":"done"}\n\nevent: result\ndata: {"outcome":"answered"}\n\n',
    ])))
    const progress = vi.fn()
    const result = vi.fn()

    await streamAgent('token', { message: 'hello' }, { onProgress: progress, onResult: result })

    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ node: 'classify' }))
    expect(result).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'answered' }))
  })

  it('raises controlled SSE errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      'event: error\ndata: {"error":{"code":"request_precondition_failed","message":"missing draft"}}\n\n',
    ])))

    await expect(streamAgent('token', {}, { onProgress: vi.fn(), onResult: vi.fn() }))
      .rejects.toMatchObject({ code: 'request_precondition_failed', message: 'missing draft' })
  })
})
