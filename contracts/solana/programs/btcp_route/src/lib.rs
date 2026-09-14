use anchor_lang::prelude::*;

declare_id!("AdnFwj8SVMBSQyw5rrEZKbp9D6Qw7UUEtEVyUa7T5fXk");

#[account]
pub struct Record {
    pub entity_id: [u8; 32],
    pub data_hash: [u8; 32],
    pub status: u8,
    pub created_slot: u64,
    pub submitter: Pubkey,
}

#[error_code]
pub enum RecordError {
    #[msg("Not found")]
    NotFound,
    #[msg("Not owner")]
    NotOwner,
    #[msg("Bad input")]
    BadInput,
    #[msg("Already exists")]
    AlreadyExists,
}

#[program]
pub mod generic_contract {
    use super::*;

    pub fn initialize(_ctx: Context<Initialize>) -> Result<()> {
        Ok(())
    }

    pub fn register(ctx: Context<Register>, _id: [u8; 32], entity_id: [u8; 32], data_hash: [u8; 32]) -> Result<()> {
        let record = &mut ctx.accounts.record;
        record.entity_id = entity_id;
        record.data_hash = data_hash;
        record.status = 0;
        record.created_slot = Clock::get()?.slot;
        record.submitter = ctx.accounts.signer.key();
        Ok(())
    }

    pub fn update_status(ctx: Context<UpdateStatus>, _id: [u8; 32], status: u8) -> Result<()> {
        let record = &mut ctx.accounts.record;
        record.status = status;
        Ok(())
    }
}

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(mut)]
    pub signer: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(id: [u8; 32])]
pub struct Register<'info> {
    #[account(init, payer = signer, space = 8 + 32 + 32 + 1 + 8 + 32, seeds = [b"record".as_ref(), id.as_ref()], bump)]
    pub record: Account<'info, Record>,
    #[account(mut)]
    pub signer: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(id: [u8; 32])]
pub struct UpdateStatus<'info> {
    #[account(mut, seeds = [b"record".as_ref(), id.as_ref()], bump)]
    pub record: Account<'info, Record>,
    #[account(mut)]
    pub signer: Signer<'info>,
}
