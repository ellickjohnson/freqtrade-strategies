'use client'

import { useState } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Search, Loader2, FileText, Calendar, Tag, ExternalLink } from 'lucide-react'

interface MemoryResult {
  path: string
  title: string
  content_snippet: string
  memory_type: string
  created_at: string
  tags: string[]
  relevance: number
}

interface MemorySearchProps {
  onResultSelect?: (result: MemoryResult) => void
}

export function MemorySearch({ onResultSelect }: MemorySearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<MemoryResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedType, setSelectedType] = useState<string | null>(null)

  const handleSearch = async () => {
    if (!query.trim()) return

    setLoading(true)
    setError(null)

    try {
      const response = await api.searchMemory(query)
      let searchResults = response.results || []

      // Filter by type if selected
      if (selectedType) {
        searchResults = searchResults.filter(
          (r: MemoryResult) => r.memory_type === selectedType
        )
      }

      setResults(searchResults)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'decision':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
      case 'research':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30'
      case 'analysis':
        return 'bg-green-500/20 text-green-400 border-green-500/30'
      case 'regime':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
      case 'hyperopt':
        return 'bg-orange-500/20 text-orange-400 border-orange-500/30'
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30'
    }
  }

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    } catch {
      return dateString
    }
  }

  return (
    <div className="space-y-4">
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-slate-50 flex items-center gap-2">
            <Search className="h-5 w-5" />
            Agent Memory Search
          </CardTitle>
          <CardDescription>
            Search through agent decisions, research findings, and analysis
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Search Input */}
            <div className="flex gap-2">
              <Input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder="Search agent memory... (e.g., 'market regime', 'BTC analysis')"
                className="flex-1 bg-slate-800 border-slate-700 text-slate-50 placeholder:text-slate-500"
              />
              <Button
                onClick={handleSearch}
                disabled={loading || !query.trim()}
                className="bg-blue-600 hover:bg-blue-700"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>

            {/* Type Filters */}
            <div className="flex flex-wrap gap-2">
              <Badge
                variant={selectedType === null ? 'default' : 'outline'}
                className={`cursor-pointer ${
                  selectedType === null
                    ? 'bg-blue-600'
                    : 'bg-slate-800 border-slate-700 hover:bg-slate-700'
                }`}
                onClick={() => setSelectedType(null)}
              >
                All
              </Badge>
              {['decision', 'research', 'analysis', 'regime', 'hyperopt'].map((type) => (
                <Badge
                  key={type}
                  variant={selectedType === type ? 'default' : 'outline'}
                  className={`cursor-pointer ${
                    selectedType === type
                      ? 'bg-blue-600'
                      : 'bg-slate-800 border-slate-700 hover:bg-slate-700'
                  }`}
                  onClick={() => setSelectedType(type)}
                >
                  {type.charAt(0).toUpperCase() + type.slice(1)}
                </Badge>
              ))}
            </div>

            {/* Error */}
            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
                {error}
              </div>
            )}

            {/* Results */}
            <div className="space-y-3">
              {results.length === 0 && !loading && query && (
                <div className="text-center py-8 text-slate-400">
                  No results found for "{query}"
                </div>
              )}

              {results.map((result, index) => (
                <Card
                  key={index}
                  className="bg-slate-800/50 border-slate-700 hover:border-slate-600 cursor-pointer transition-colors"
                  onClick={() => onResultSelect?.(result)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge className={getTypeColor(result.memory_type)}>
                            {result.memory_type}
                          </Badge>
                          <span className="text-xs text-slate-400 flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            {formatDate(result.created_at)}
                          </span>
                        </div>
                        <h4 className="font-medium text-slate-50 truncate">
                          {result.title || result.path.split('/').pop()?.replace('.md', '')}
                        </h4>
                        <p className="text-sm text-slate-400 line-clamp-2 mt-1">
                          {result.content_snippet}
                        </p>
                        {result.tags && result.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {result.tags.slice(0, 5).map((tag, i) => (
                              <span
                                key={i}
                                className="text-xs text-slate-500"
                              >
                                #{tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <span className="text-xs text-slate-400">
                          {(result.relevance * 100).toFixed(0)}% match
                        </span>
                        <ExternalLink className="h-4 w-4 text-slate-500" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Search Tips */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-sm text-slate-300">Search Tips</CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-slate-400 space-y-1">
          <p>• Use keywords like "trending", "volatile", "regime" for market analysis</p>
          <p>• Search for strategy IDs to find related decisions</p>
          <p>• Use asset names like "BTC", "ETH" for asset-specific findings</p>
          <p>• Search for agent types like "research", "risk", "analysis"</p>
        </CardContent>
      </Card>
    </div>
  )
}