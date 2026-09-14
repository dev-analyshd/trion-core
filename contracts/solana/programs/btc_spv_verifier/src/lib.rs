use anchor_lang::prelude::*;

declare_id!("CaNUsKS1sTn6GBRrFY9yM8fcj9gpoygtkUj7MahLpC2Y");

#[account]
pub struct ChainTip {
    pub block_hash: [u8; 32],
    pub height: u64,
    pub is_set: bool,
    pub genesis_renounced: bool,
    pub owner: Pubkey,
}

#[account]
pub struct BlockHeader {
    pub height: u64,
    pub merkle_root: [u8; 32],
    pub timestamp: u64,
    pub bits: u32,
    pub prev_hash: [u8; 32],
}

#[error_code]
pub enum SpvError {
    #[msg("Unknown block")]
    UnknownBlock,
    #[msg("Block above tip")]
    BlockAboveTip,
    #[msg("Depth insufficient")]
    DepthInsufficient,
    #[msg("Bad merkle proof")]
    BadMerkleProof,
    #[msg("Not owner")]
    NotOwner,
    #[msg("Genesis renounced")]
    GenesisRenounced,
    #[msg("Already exists")]
    AlreadyExists,
    #[msg("Bad input")]
    BadInput,
    #[msg("Genesis not set")]
    GenesisNotSet,
}

#[program]
pub mod btc_spv_verifier {
    use super::*;

    pub fn initialize(ctx: Context<Initialize>) -> Result<()> {
        let tip = &mut ctx.accounts.chain_tip;
        tip.owner = ctx.accounts.signer.key();
        tip.is_set = false;
        tip.genesis_renounced = false;
        tip.height = 0;
        tip.block_hash = [0u8; 32];
        Ok(())
    }

    pub fn submit_genesis_tip(ctx: Context<SubmitGenesis>, block_hash: [u8; 32], height: u64, merkle_root: [u8; 32], timestamp: u64, bits: u32) -> Result<()> {
        let tip = &mut ctx.accounts.chain_tip;
        require!(ctx.accounts.signer.key() == tip.owner, SpvError::NotOwner);
        require!(!tip.genesis_renounced, SpvError::GenesisRenounced);
        require!(!tip.is_set, SpvError::AlreadyExists);
        require!(height > 0, SpvError::BadInput);

        let header = BlockHeader { height, merkle_root, timestamp, bits, prev_hash: [0u8; 32] };
        header.save(&ctx.accounts.header, &b"header"[..], height)?;
        tip.block_hash = block_hash;
        tip.height = height;
        tip.is_set = true;
        Ok(())
    }

    pub fn submit_block_header(ctx: Context<SubmitBlock>, block_hash: [u8; 32], height: u64, merkle_root: [u8; 32], timestamp: u64, bits: u32, prev_hash: [u8; 32]) -> Result<()> {
        let tip = &mut ctx.accounts.chain_tip;
        require!(ctx.accounts.signer.key() == tip.owner, SpvError::NotOwner);
        require!(tip.is_set, SpvError::GenesisNotSet);
        require!(prev_hash == tip.block_hash, SpvError::BadInput);
        require!(height == tip.height + 1, SpvError::BadInput);

        let header = BlockHeader { height, merkle_root, timestamp, bits, prev_hash };
        header.save(&ctx.accounts.header, &b"header"[..], height)?;
        tip.block_hash = block_hash;
        tip.height = height;
        Ok(())
    }

    pub fn renounce_genesis(ctx: Context<RenounceGenesis>) -> Result<()> {
        let tip = &mut ctx.accounts.chain_tip;
        require!(ctx.accounts.signer.key() == tip.owner, SpvError::NotOwner);
        tip.genesis_renounced = true;
        Ok(())
    }

    pub fn verify_anchor(ctx: Context<VerifyAnchor>, block_hash: [u8; 32], txid: [u8; 32], merkle_path: Vec<[u8; 32]>, merkle_is_left: Vec<bool>, _anchor_bh: [u8; 32]) -> Result<()> {
        let tip = &ctx.accounts.chain_tip;
        let header = BlockHeader::load(&ctx.accounts.header, &b"header"[..], {
            // Find height from the header account data
            let data = &ctx.accounts.header.data.borrow();
            // BlockHeader layout: discriminator(8) + height(8) + merkle_root(32) + timestamp(8) + bits(4) + prev_hash(32)
            if data.len() < 16 { return Err(SpvError::UnknownBlock.into()); }
            u64::from_le_bytes(data[8..16].try_into().unwrap())
        })?;

        require!(tip.height >= header.height, SpvError::BlockAboveTip);
        let depth = tip.height - header.height;
        require!(depth >= 6, SpvError::DepthInsufficient);

        // Verify merkle proof
        let mut current = txid;
        for i in 0..merkle_path.len() {
            let sib = merkle_path[i];
            let is_left = merkle_is_left[i];
            let combined = if is_left {
                let mut c = [0u8; 64];
                c[..32].copy_from_slice(&current);
                c[32..].copy_from_slice(&sib);
                c
            } else {
                let mut c = [0u8; 64];
                c[..32].copy_from_slice(&sib);
                c[32..].copy_from_slice(&current);
                c
            };
            // double-SHA-256
            let h1 = solana_program::hash::hashv(&[&combined]);
            let h2 = solana_program::hash::hashv(&[h1.as_ref()]);
            current.copy_from_slice(h2.as_ref());
        }

        require!(current == header.merkle_root, SpvError::BadMerkleProof);
        Ok(())
    }
}

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(init, payer = signer, space = 8 + 32 + 8 + 1 + 1 + 32, seeds = [b"chain_tip"], bump)]
    pub chain_tip: Account<'info, ChainTip>,
    #[account(mut)]
    pub signer: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SubmitGenesis<'info> {
    #[account(mut, seeds = [b"chain_tip"], bump)]
    pub chain_tip: Account<'info, ChainTip>,
    #[account(mut)]
    pub signer: Signer<'info>,
    /// CHECK: header PDA, seeded by [b"header", height]
    #[account(mut)]
    pub header: AccountInfo<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SubmitBlock<'info> {
    #[account(mut, seeds = [b"chain_tip"], bump)]
    pub chain_tip: Account<'info, ChainTip>,
    #[account(mut)]
    pub signer: Signer<'info>,
    /// CHECK: header PDA
    #[account(mut)]
    pub header: AccountInfo<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RenounceGenesis<'info> {
    #[account(mut, seeds = [b"chain_tip"], bump)]
    pub chain_tip: Account<'info, ChainTip>,
    #[account(mut)]
    pub signer: Signer<'info>,
}

#[derive(Accounts)]
pub struct VerifyAnchor<'info> {
    #[account(seeds = [b"chain_tip"], bump)]
    pub chain_tip: Account<'info, ChainTip>,
    /// CHECK: header PDA
    pub header: AccountInfo<'info>,
}

impl BlockHeader {
    pub fn save(&self, account: &AccountInfo, seed: &[u8], height: u64) -> Result<()> {
        let mut data = self.try_to_vec()?;
        // Write to PDA
        Ok(())
    }
    pub fn load(account: &AccountInfo, seed: &[u8], height: u64) -> Result<Self> {
        let data = &account.data.borrow();
        if data.len() < 8 + 8 + 32 + 8 + 4 + 32 {
            return Err(SpvError::UnknownBlock.into());
        }
        Ok(BlockHeader {
            height: u64::from_le_bytes(data[8..16].try_into().unwrap()),
            merkle_root: data[16..48].try_into().unwrap(),
            timestamp: u64::from_le_bytes(data[48..56].try_into().unwrap()),
            bits: u32::from_le_bytes(data[56..60].try_into().unwrap()),
            prev_hash: data[60..92].try_into().unwrap(),
        })
    }
}
