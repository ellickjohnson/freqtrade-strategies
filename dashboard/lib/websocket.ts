import { useEffect, useRef, useCallback } from 'react'
import { useStrategyStore } from './store'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8765'

type MessageHandler = (data: any) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private messageHandlers: Map<string, MessageHandler[]> = new Map()
  private isConnected = false
  
  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return
    }
    
    this.ws = new WebSocket(WS_URL)
    
    this.ws.onopen = () => {
      console.log('WebSocket connected')
      this.isConnected = true
      this.reconnectAttempts = 0
      this.emit('connected', { message: 'WebSocket connected' })
    }
    
    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        this.handleMessage(message)
      } catch (error) {
        console.error('Error parsing WebSocket message:', error)
      }
    }
    
    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      this.emit('error', { error: 'WebSocket error' })
    }
    
    this.ws.onclose = () => {
      console.log('WebSocket disconnected')
      this.isConnected = false
      this.emit('disconnected', { message: 'WebSocket disconnected' })
      this.scheduleReconnect()
    }
  }
  
  disconnect() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
      this.isConnected = false
    }
  }
  
  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached')
      return
    }
    
    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
    
    setTimeout(() => {
      console.log(`Reconnecting... (attempt ${this.reconnectAttempts})`)
      this.connect()
    }, delay)
  }
  
  send(command: string, data?: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ command, data }))
    } else {
      console.error('WebSocket not connected')
    }
  }
  
  on(event: string, handler: MessageHandler) {
    if (!this.messageHandlers.has(event)) {
      this.messageHandlers.set(event, [])
    }
    this.messageHandlers.get(event)?.push(handler)
  }
  
  off(event: string, handler: MessageHandler) {
    const handlers = this.messageHandlers.get(event)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index >= 0) {
        handlers.splice(index, 1)
      }
    }
  }
  
  private emit(event: string, data: any) {
    const handlers = this.messageHandlers.get(event)
    if (handlers) {
      handlers.forEach(handler => handler(data))
    }
  }
  
  private handleMessage(message: { event: string; data: any; timestamp: string }) {
    this.emit(message.event, message.data)
    
    // Update global store based on event type
    switch (message.event) {
      case 'trade':
        useStrategyStore.getState().updateTrade(message.data)
        break
      case 'status':
        useStrategyStore.getState().updateStrategyStatus(message.data)
        break
      case 'log':
        useStrategyStore.getState().addLog(message.data)
        break
      case 'error':
        useStrategyStore.getState().setError(message.data)
        break
    }
  }
  
  getConnectionStatus() {
    return this.isConnected
  }
}

let wsClient: WebSocketClient | null = null

export function useWebSocket() {
  const clientRef = useRef<WebSocketClient | null>(null)
  
  if (!clientRef.current) {
    if (!wsClient) {
      wsClient = new WebSocketClient()
    }
    clientRef.current = wsClient
  }
  
  useEffect(() => {
    clientRef.current?.connect()
    
    return () => {
      // Don't disconnect on unmount - keep connection alive
    }
  }, [])
  
  return clientRef.current
}

export function useWebSocketEvent(event: string, handler: MessageHandler) {
  const client = useWebSocket()
  
  useEffect(() => {
    client.on(event, handler)
    
    return () => {
      client.off(event, handler)
    }
  }, [event, handler, client])
}