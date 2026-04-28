import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [funds, setFunds] = useState([])
  const [selectedTab, setSelectedTab] = useState('chat')
  const [apiInfo, setApiInfo] = useState(null)
  const [error, setError] = useState(null)
  const messagesEndRef = useRef(null)

  // Fetch initial data
  useEffect(() => {
    const initializeApp = async () => {
      try {
        // Fetch API info
        const response = await fetch('/api');
        const data = await response.json();
        
        setApiInfo(data);
        
        // Fetch funds
        const fundsResponse = await fetch('/api/funds?limit=100');
        const fundsData = await fundsResponse.json();
        setFunds(fundsData);
      } catch (err) {
        console.error('Initialization error:', err);
        setError('Failed to initialize the application. Please refresh the page.');
      }
    };

    initializeApp();
  }, []);

  useEffect(() => {
    setMessages([
      {
        type: 'bot',
        content: 'Hello! 👋 I\'m your INDMoney FAQ Assistant. Ask me anything about HDFC mutual funds!',
        timestamp: new Date()
      }
    ])
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const renderWithLinks = (text) => {
    const s = String(text ?? '')
    const urlRe = /(https?:\/\/[^\s]+)/g
    const parts = s.split(urlRe)
    return parts.map((part, idx) => {
      if (part.match(urlRe)) {
        return (
          <a key={idx} href={part} target="_blank" rel="noreferrer">
            {part}
          </a>
        )
      }
      return <span key={idx}>{part}</span>
    })
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim() || loading) return

    const userMessage = {
      type: 'user',
      content: input,
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    const q = input.trim()
    setInput('')
    setLoading(true)

    try {
      let botMessage;

      // Handle greetings locally so the bot feels conversational.
      // This avoids wasting quota and prevents odd “fund answers” to “hi”.
      const isGreeting = /^(hi|hello|hey|yo|hii|hiii|hola|good\s*(morning|afternoon|evening))[\s!.]*$/i.test(q)
      if (isGreeting) {
        botMessage = {
          type: 'bot',
          content:
            "Hi there! 👋 I'm your INDMoney FAQ Assistant—here to help with all your mutual fund questions. Ask away!",
          timestamp: new Date()
        }
        setMessages(prev => [...prev, botMessage])
        return
      }

      const aiRes = await fetch('/api/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          use_context: true,
          use_rag: true,
        }),
      });

      if (aiRes.ok) {
        const payload = await aiRes.json();
        const src = payload.source;
        const text = (payload.answer || '').trim();
        if (src && src !== 'error' && text) {
          botMessage = {
            type: 'bot',
            content: text,
            timestamp: new Date()
          };
          setMessages(prev => [...prev, botMessage]);
          return;
        }
        // If AI returned an error (often quota / rate-limit), show it instead of
        // silently falling back to an empty FAQ response.
        if (src === 'error' && text) {
          const retryMatch = text.match(/retry in\s+(\d+)\s*\.?(\d+)?s/i) || text.match(/retry_delay.*seconds:\s*(\d+)/i)
          const retrySeconds = retryMatch ? (retryMatch[1] || retryMatch[0]) : null
          const friendly =
            retrySeconds
              ? `I’m temporarily rate-limited by the AI provider. Please try again in about ${retrySeconds}s.`
              : `I’m temporarily unable to reach the AI provider. Please try again in a moment.`
          botMessage = {
            type: 'bot',
            content: friendly,
            timestamp: new Date(),
            isError: true
          }
          setMessages(prev => [...prev, botMessage]);
          return;
        }
      }

      const response = await fetch(`/api/faq?q=${encodeURIComponent(q)}&limit=5`);
      if (response.ok) {
        const data = await response.json();
        if (data.length > 0) {
          const answer =
            `I couldn’t reach the AI right now, but here’s what I found in the FAQ database:\n\n` +
            data.map((faq) => {
              const fund = faq.fund_name ? `• Fund: ${faq.fund_name}\n` : '• '
              const qa = `  ${faq.question}\n  ${faq.answer}\n`
              const src = faq.source_url ? `  Source: ${faq.source_url}` : ''
              return `${fund}${qa}${src}`.trimEnd()
            }).join('\n\n')
          botMessage = {
            type: 'bot',
            content: answer,
            timestamp: new Date()
          };
        } else {
          botMessage = {
            type: 'bot',
            content: "I couldn't find any relevant information for your question. Please try rephrasing or ask something else.",
            timestamp: new Date()
          };
        }
        setMessages(prev => [...prev, botMessage]);
      } else {
        throw new Error(`Request failed: ${response.status}`);
      }
    } catch (error) {
      const errorMessage = {
        type: 'bot',
        content: `Sorry, I encountered an error: ${error.message || 'Unknown error'}. Please try again.`,
        timestamp: new Date(),
        isError: true
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  const askQuickQuestion = async (question) => {
    setInput(question)
    setTimeout(() => {
      document.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))
    }, 100)
  }

  return (
    <div className="app-container">
      <div className="chat-card">
        <div className="header">
          <div className="header-content">
            <div className="logo">
              <div className="logo-icon">💰</div>
              <div>
                <h1>INDMoney</h1>
                <p>FAQ Assistant</p>
              </div>
            </div>
            <div className="tabs">
              <button 
                className={selectedTab === 'chat' ? 'active' : ''}
                onClick={() => setSelectedTab('chat')}
              >
                💬 Chat
              </button>
              <button 
                className={selectedTab === 'funds' ? 'active' : ''}
                onClick={() => setSelectedTab('funds')}
              >
                📊 Funds
              </button>
            </div>
          </div>
        </div>

        {selectedTab === 'chat' ? (
          <>
            <div className="messages-container">
              {messages.map((message, index) => (
                <div key={index} className={`message ${message.type}`}>
                  <div className="message-bubble">
                    <div className="message-content">{renderWithLinks(message.content)}</div>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="message bot">
                  <div className="message-bubble typing">
                    <div className="typing-indicator">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="quick-questions">
              <div className="quick-questions-label">Quick questions:</div>
              <div className="quick-buttons">
                <button onClick={() => askQuickQuestion('What is the minimum SIP amount?')}>
                  💵 Minimum SIP
                </button>
                <button onClick={() => askQuickQuestion('What is expense ratio?')}>
                  ❓ Expense Ratio
                </button>
                <button onClick={() => askQuickQuestion('Tell me about HDFC Mid Cap Fund')}>
                  📈 Mid Cap Fund
                </button>
              </div>
            </div>

            <form className="input-container" onSubmit={sendMessage}>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask anything about mutual funds..."
                disabled={loading}
              />
              <button type="submit" disabled={loading || !input.trim()}>
                <span>Send</span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
                </svg>
              </button>
            </form>
          </>
        ) : (
          <div className="funds-container">
            <div className="funds-header">
              <h2>Available HDFC Funds</h2>
              <p>{funds.length} funds in database</p>
            </div>
            <div className="funds-grid">
              {funds.map((fund, index) => (
                <div key={index} className="fund-card">
                  <div className="fund-name">{fund.fund_name}</div>
                  <div className="fund-details">
                    <div className="fund-detail">
                      <span className="label">Manager:</span>
                      <span className="value">{fund.fund_manager || 'N/A'}</span>
                    </div>
                    <div className="fund-detail">
                      <span className="label">Expense Ratio:</span>
                      <span className="value">{fund.expense_ratio || 'N/A'}</span>
                    </div>
                    <div className="fund-detail">
                      <span className="label">Risk:</span>
                      <span className="value risk">{fund.riskometer || 'N/A'}</span>
                    </div>
                  </div>
                  <div className="returns">
                    <div className="returns-title">Returns</div>
                    <div className="returns-grid">
                      {Object.entries(fund.returns || {}).map(([period, value]) => (
                        <div key={period} className="return-item">
                          <span className="period">{period}</span>
                          <span className="return-value">{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <button 
                    className="ask-about-fund"
                    onClick={() => {
                      setSelectedTab('chat')
                      askQuickQuestion(`Tell me about ${fund.fund_name}`)
                    }}
                  >
                    Ask about this fund
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default App